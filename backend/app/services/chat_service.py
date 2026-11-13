"""고객 대화 흐름: 대화 생성, 질문(RAG 호출과 로그 저장), 피드백."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppSettings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import SlidingWindowLimiter, kst_day_start, seconds_until_kst_midnight
from app.core.security import hash_token, new_chat_token
from app.db.models import Chat, ChatTurn, TurnSource
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import FeedbackRequest, FeedbackResponse, TurnRequest, TurnResponse
from app.services.access import authorize_chat, enforce_limit
from app.services.rag_runtime import RagRuntime, classify_rag_error
from rag.schemas import RagResponse

logger = logging.getLogger(__name__)

MINUTE = 60


@dataclass(frozen=True)
class CreatedChat:
    chat: Chat
    token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _nonzero(value: int) -> int | None:
    # RAG는 사용량을 받지 못하면 0을 채운다. 비용이 $0으로 보이지 않도록 측정 안 됨(null)으로 저장한다
    return value or None


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        settings: AppSettings,
        limiter: SlidingWindowLimiter,
        rag: RagRuntime,
    ) -> None:
        self.session = session
        self.repo = ChatRepository(session)
        self.settings = settings
        self.limiter = limiter
        self.rag = rag

    async def authorize(self, chat_id: uuid.UUID, token: str | None) -> Chat:
        return await authorize_chat(self.repo, chat_id, token)

    def _limit(self, key: str, limit: int, window: int) -> None:
        enforce_limit(self.limiter, key, limit, window)

    async def create_chat(self, client_ip_hash: str) -> CreatedChat:
        s = self.settings
        self._limit(f"chat:ip:{client_ip_hash}", s.chat_create_per_ip_per_minute, MINUTE)
        today = await self.repo.count_chats_since(client_ip_hash, kst_day_start())
        if today >= s.chat_create_per_ip_per_day:
            raise AppError(ErrorCode.DAILY_LIMIT_REACHED, retry_after=seconds_until_kst_midnight())
        token = new_chat_token()
        chat = Chat(
            id=uuid.uuid4(),
            token_hash=hash_token(token),
            client_ip_hash=client_ip_hash,
            created_at=_now(),
        )
        await self.repo.add_chat(chat)
        await self.session.commit()
        return CreatedChat(chat=chat, token=token)

    async def ask(self, chat: Chat, request: TurnRequest, requester_ip_hash: str) -> TurnResponse:
        parent = await self._parent(chat, request.parent_turn_id)
        await self._check_turn_limits(chat, requester_ip_hash)
        history = await self._history(parent)
        # 위 조회로 열린 트랜잭션을 닫아 DB 연결을 풀에 돌려준다. RAG를 기다리는 최대 30초 동안
        # 연결을 잡고 있으면 동시 질문 몇 건에 풀이 바닥난다. 결과는 새 트랜잭션에 저장한다
        await self.session.commit()

        created_at = _now()
        try:
            response = await asyncio.wait_for(
                self.rag.system.aanswer(request.question, history=history),
                timeout=self.settings.rag_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("RAG 제한 시간 초과 (%.0f초)", self.settings.rag_timeout_seconds)
            turn = await self._save_failed(chat, request, created_at, "llm_timeout")
            raise AppError(ErrorCode.AI_TIMEOUT, turn_id=turn.id) from None
        except Exception as exc:
            error_code = classify_rag_error(exc)
            logger.warning("RAG 실패 (%s)", error_code, exc_info=exc)
            turn = await self._save_failed(chat, request, created_at, error_code)
            raise AppError(ErrorCode.AI_UNAVAILABLE, turn_id=turn.id) from None

        turn = await self._save_completed(chat, request, created_at, response)
        return TurnResponse(
            turn_id=turn.id,
            chat_id=chat.id,
            parent_turn_id=turn.parent_turn_id,
            question=turn.question,
            mode=turn.mode,
            answer=turn.answer or "",
            show_contact=turn.show_contact,
            feedback=None,
            created_at=turn.created_at,
        )

    async def _parent(self, chat: Chat, parent_turn_id: uuid.UUID | None) -> ChatTurn | None:
        if parent_turn_id is None:
            return None
        parent = await self.repo.get_turn(parent_turn_id)
        # 같은 대화의 완료 turn만 부모가 될 수 있다. 실패 turn 뒤 "다시 시도"는 실패 turn의 부모를 쓴다
        if parent is None or parent.chat_id != chat.id or parent.status != "completed":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "이전 답변을 이 대화에서 찾을 수 없어요.",
                fields=["parent_turn_id"],
            )
        return parent

    async def _check_turn_limits(self, chat: Chat, requester_ip_hash: str) -> None:
        s = self.settings
        self._limit(f"turn:chat:{chat.id}", s.turn_per_chat_per_minute, MINUTE)
        self._limit(f"turn:ip:{requester_ip_hash}", s.turn_per_ip_per_minute, MINUTE)
        since = kst_day_start()
        by_ip = await self.repo.count_completed_turns_since(since, chat.client_ip_hash)
        if by_ip >= s.turn_per_ip_per_day:
            raise AppError(
                ErrorCode.DAILY_LIMIT_REACHED,
                "오늘 이용 가능한 질문 수를 넘었어요.",
                retry_after=seconds_until_kst_midnight(),
            )
        total = await self.repo.count_completed_turns_since(since)
        if total >= s.turn_global_per_day:
            # 한 고객의 잘못이 아니라 서비스 전체 사정이라 503으로 준다
            raise AppError(ErrorCode.SERVICE_BUSY, retry_after=seconds_until_kst_midnight())

    async def _history(self, parent: ChatTurn | None) -> list[str]:
        """부모를 따라 올라가며 이전 고객 질문을 꺼낸다(오래된 것부터). 고객이 보낸 원문은 받지 않는다."""
        questions: list[str] = []
        turn = parent
        while turn is not None and len(questions) < self.rag.history_turns:
            questions.append(turn.question)
            turn = await self.repo.get_turn(turn.parent_turn_id) if turn.parent_turn_id else None
        return list(reversed(questions))

    def _turn(self, chat: Chat, request: TurnRequest, created_at: datetime) -> ChatTurn:
        return ChatTurn(
            id=uuid.uuid4(),
            chat_id=chat.id,
            parent_turn_id=request.parent_turn_id,
            question=request.question,
            llm_model=self.rag.llm_model,
            config_name=self.rag.config_name,
            created_at=created_at,
        )

    async def _save_failed(
        self, chat: Chat, request: TurnRequest, created_at: datetime, error_code: str
    ) -> ChatTurn:
        turn = self._turn(chat, request, created_at)
        turn.status = "failed"
        turn.error_code = error_code
        turn.show_contact = False
        # 잠금을 잡은 뒤에 완료 시각을 찍어야 같은 대화 안에서 저장 순서와 finished_at 순서가 같다
        await self.repo.lock_chat(chat.id)
        turn.finished_at = await self.repo.db_now()
        await self.repo.add_turn(turn, [])
        await self.session.commit()
        return turn

    async def _save_completed(
        self, chat: Chat, request: TurnRequest, created_at: datetime, response: RagResponse
    ) -> ChatTurn:
        turn = self._turn(chat, request, created_at)
        turn.status = "completed"
        turn.mode = response.mode
        turn.answer = response.answer
        turn.show_contact = response.show_contact
        turn.reason = response.reason or None
        turn.latency_ms = response.latency_ms
        turn.prompt_tokens = _nonzero(response.prompt_tokens)
        turn.completion_tokens = _nonzero(response.completion_tokens)
        await self.repo.lock_chat(chat.id)
        turn.finished_at = await self.repo.db_now()
        await self.repo.add_turn(turn, self._sources(turn.id, response))
        await self.session.commit()
        return turn

    def _sources(self, turn_id: uuid.UUID, response: RagResponse) -> list[TurnSource]:
        """답변 근거(cited)와 검색 후보(retrieved)를 저장한다. 같은 FAQ는 종류별로 한 번만 남긴다."""
        rows: list[TurnSource] = []
        cited = [(s.faq_id, s.title, s.score) for s in response.sources]
        retrieved = [
            (faq_id, self.rag.titles.get(faq_id), score)
            for faq_id, score in zip(
                response.retrieved_ids, response.retrieved_scores, strict=False
            )
        ]
        for kind, entries in (("cited", cited), ("retrieved", retrieved)):
            seen: set[str] = set()
            for faq_id, title, score in entries:
                if faq_id in seen:
                    continue
                seen.add(faq_id)
                rows.append(
                    TurnSource(
                        turn_id=turn_id,
                        kind=kind,
                        rank=len(seen),
                        source_id=faq_id,
                        title=title,
                        score=score,
                    )
                )
        return rows

    async def _own_turn(self, chat: Chat, turn_id: uuid.UUID) -> ChatTurn:
        turn = await self.repo.get_turn(turn_id)
        if turn is None or turn.chat_id != chat.id:
            raise AppError(ErrorCode.NOT_FOUND, "답변을 찾을 수 없어요.")
        return turn

    async def put_feedback(
        self, chat: Chat, turn_id: uuid.UUID, request: FeedbackRequest
    ) -> FeedbackResponse:
        turn = await self._own_turn(chat, turn_id)
        if turn.status != "completed":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "완료된 답변에만 평가를 남길 수 있어요.",
                fields=["turn_id"],
            )
        reason = request.reason if request.rating == "down" else None
        rating, reason, updated_at = await self.repo.upsert_feedback(
            turn_id, request.rating, reason, _now()
        )
        await self.session.commit()
        return FeedbackResponse(
            rating=rating,
            reason=reason,
            updated_at=updated_at,
        )

    async def delete_feedback(self, chat: Chat, turn_id: uuid.UUID) -> None:
        await self._own_turn(chat, turn_id)
        await self.repo.delete_feedback(turn_id)
        await self.session.commit()
