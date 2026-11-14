"""대화·turn·출처·피드백 저장소. 트랜잭션 경계(commit)는 Service가 정한다."""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, ChatTurn, Feedback, TurnSource


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_chat(self, chat: Chat) -> None:
        self.session.add(chat)
        await self.session.flush()

    async def get_chat(self, chat_id: uuid.UUID) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def lock_chat(self, chat_id: uuid.UUID) -> None:
        """대화 행을 트랜잭션 끝까지 잠근다. 같은 대화의 turn 저장과 문의 접수를 한 줄로 세운다."""
        await self.session.execute(select(Chat.id).where(Chat.id == chat_id).with_for_update())

    async def db_now(self) -> datetime:
        """DB 시계의 현재 시각. 서버 인스턴스마다 시계가 달라도 같은 대화의 순서가 흔들리지 않는다."""
        return await self.session.scalar(select(func.clock_timestamp()))

    async def count_chats_since(self, client_ip_hash: str, since: datetime) -> int:
        query = select(func.count()).where(
            Chat.client_ip_hash == client_ip_hash, Chat.created_at >= since
        )
        return await self.session.scalar(query) or 0

    async def get_turn(self, turn_id: uuid.UUID) -> ChatTurn | None:
        return await self.session.get(ChatTurn, turn_id)

    async def add_turn(self, turn: ChatTurn, sources: list[TurnSource]) -> None:
        self.session.add(turn)
        await self.session.flush()
        self.session.add_all(sources)
        await self.session.flush()

    async def count_completed_turns_since(
        self, since: datetime, client_ip_hash: str | None = None
    ) -> int:
        """하루 한도 계산. 고객 잘못이 아닌 실패로 한도가 줄지 않도록 완료 turn만 센다."""
        query = (
            select(func.count())
            .select_from(ChatTurn)
            .where(ChatTurn.status == "completed", ChatTurn.created_at >= since)
        )
        if client_ip_hash is not None:
            # 요청자 IP가 아니라 대화를 만든 IP 기준이다. 토큰을 다른 IP에서 써도 한도를 피하지 못한다
            query = query.join(Chat, Chat.id == ChatTurn.chat_id).where(
                Chat.client_ip_hash == client_ip_hash
            )
        return await self.session.scalar(query) or 0

    async def has_completed_turn(self, chat_id: uuid.UUID) -> bool:
        query = (
            select(ChatTurn.id)
            .where(ChatTurn.chat_id == chat_id, ChatTurn.status == "completed")
            .limit(1)
        )
        return await self.session.scalar(query) is not None

    async def last_saved_turn_id(self, chat_id: uuid.UUID) -> uuid.UUID | None:
        """대화에 저장된 마지막 turn(완료·실패 모두). 문의의 채팅 기록 경계가 된다."""
        query = (
            select(ChatTurn.id)
            .where(ChatTurn.chat_id == chat_id)
            .order_by(ChatTurn.finished_at.desc(), ChatTurn.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(query)

    async def upsert_feedback(
        self, turn_id: uuid.UUID, rating: str, reason: str | None, now: datetime
    ) -> tuple[str, str | None, datetime]:
        """답변마다 평가 1건. 👍 직후 👎처럼 동시에 와도 PK 충돌 없이 마지막 값이 남는다."""
        statement = insert(Feedback).values(
            turn_id=turn_id, rating=rating, reason=reason, created_at=now, updated_at=now
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Feedback.turn_id],
            # created_at은 처음 평가 시각으로 둔다. 동시 요청 순서가 바뀌어도 updated_at은 뒤로 가지 않는다
            set_={
                "rating": statement.excluded.rating,
                "reason": statement.excluded.reason,
                "updated_at": func.greatest(Feedback.updated_at, statement.excluded.updated_at),
            },
        ).returning(Feedback.rating, Feedback.reason, Feedback.updated_at)
        row = (await self.session.execute(statement)).one()
        return row.rating, row.reason, row.updated_at

    async def delete_feedback(self, turn_id: uuid.UUID) -> None:
        # 이미 없어도 오류 없이 끝난다 (취소 버튼 연타)
        await self.session.execute(delete(Feedback).where(Feedback.turn_id == turn_id))
