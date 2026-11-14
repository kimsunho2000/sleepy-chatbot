"""관리자 문의 관리: 목록·건수·상세(채팅 기록)와 읽음·상태·메모 수정.

규칙 (ADMIN.md, docs/admin-chat-api-design.md §6):
- 읽음은 first_viewed_at 하나로 관리하고 상태와 별개다. 조회만으로는 읽음 처리하지 않는다.
- completed가 되면 완료 시각을 넣고, 다른 상태로 되돌리면 지운다. 같은 completed를 다시 저장해도 시각은 그대로다.
- 채팅 기록은 접수 순간 서버가 기록한 경계 turn(context_last_turn_id)까지만 보여 준다.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.db.models import ChatTurn, Inquiry, TurnSource
from app.repositories.inquiry_repository import InquiryFilter, InquiryRepository
from app.schemas.admin_inquiry import (
    ConversationTurn,
    InquiryCounts,
    InquiryDetail,
    InquiryListResponse,
    InquirySummary,
    InquiryUpdate,
    SourceRef,
)

PREVIEW_LENGTH = 80
# 문의 상세의 검색 후보는 상위 3개만 준다. 전체 후보는 질문 로그 상세에서 본다
RETRIEVED_PREVIEW_COUNT = 3


def _preview(content: str) -> str:
    """줄바꿈과 연속 공백을 한 칸으로 줄여 한 줄로 보여 준다. 길면 …로 자른다."""
    flat = " ".join(content.split())
    if len(flat) <= PREVIEW_LENGTH:
        return flat
    return flat[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _summary_fields(inquiry: Inquiry) -> dict:
    return {
        "id": inquiry.id,
        "reference_no": inquiry.reference_no,
        "name": inquiry.name,
        "content_preview": _preview(inquiry.content),
        "origin": inquiry.origin,
        "status": inquiry.status,
        "is_unread": inquiry.first_viewed_at is None,
        # 경계 turn이 있으면 그 turn이 기록에 들어가므로 conversation은 1개 이상이다
        "has_conversation": inquiry.context_last_turn_id is not None,
        "created_at": inquiry.created_at,
    }


def _source_refs(sources: list[TurnSource], kind: str, limit: int | None = None) -> list[SourceRef]:
    picked = [s for s in sources if s.kind == kind]
    if limit is not None:
        picked = picked[:limit]
    return [
        SourceRef(rank=s.rank, source_id=s.source_id, title=s.title, score=s.score) for s in picked
    ]


def _conversation_turn(
    turn: ChatTurn, sources: list[TurnSource], trigger_turn_id: uuid.UUID | None
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn.id,
        question=turn.question,
        parent_turn_id=turn.parent_turn_id,
        status=turn.status,
        mode=turn.mode,
        answer=turn.answer,
        cited_sources=_source_refs(sources, "cited"),
        retrieved_sources=_source_refs(sources, "retrieved", RETRIEVED_PREVIEW_COUNT),
        is_trigger=turn.id == trigger_turn_id,
        created_at=turn.created_at,
    )


class AdminInquiryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.inquiries = InquiryRepository(session)

    async def list(self, condition: InquiryFilter, page: int, size: int) -> InquiryListResponse:
        rows, total = await self.inquiries.list_inquiries(condition, page, size)
        return InquiryListResponse(
            items=[InquirySummary(**_summary_fields(row)) for row in rows],
            page=page,
            size=size,
            total_count=total,
        )

    async def counts(self, condition: InquiryFilter) -> InquiryCounts:
        found = await self.inquiries.count_by_status(condition)
        return InquiryCounts(
            received=found.received,
            in_progress=found.in_progress,
            completed=found.completed,
            unresolved=found.received + found.in_progress,
            unread=found.unread,
            total=found.total,
        )

    async def detail(self, inquiry_id: uuid.UUID) -> InquiryDetail:
        inquiry = await self.inquiries.get(inquiry_id)
        if inquiry is None:
            raise _not_found()
        return await self._detail(inquiry)

    async def update(self, inquiry_id: uuid.UUID, body: InquiryUpdate) -> InquiryDetail:
        # 행을 잠그고 고친다. 읽음 처리가 동시에 두 번 와도 최초 읽음 시각이 뒤로 밀리지 않는다
        inquiry = await self.inquiries.get(inquiry_id, for_update=True)
        if inquiry is None:
            raise _not_found()

        now = datetime.now(UTC)
        changed = False
        if body.viewed and inquiry.first_viewed_at is None:
            inquiry.first_viewed_at = now
            changed = True
        if body.status is not None and body.status != inquiry.status:
            inquiry.status = body.status
            inquiry.completed_at = now if body.status == "completed" else None
            changed = True
        if body.internal_note is not None and body.internal_note != inquiry.internal_note:
            inquiry.internal_note = body.internal_note
            changed = True
        if changed:
            inquiry.updated_at = now

        await self.session.flush()
        detail = await self._detail(inquiry)
        await self.session.commit()
        return detail

    async def _detail(self, inquiry: Inquiry) -> InquiryDetail:
        conversation: list[ConversationTurn] = []
        if inquiry.chat_id is not None and inquiry.context_last_turn_id is not None:
            until = await self.inquiries.boundary_finished_at(inquiry.context_last_turn_id)
            if until is not None:
                turns = await self.inquiries.conversation_turns(inquiry.chat_id, until)
                conversation = [
                    _conversation_turn(turn, sources, inquiry.trigger_turn_id)
                    for turn, sources in turns
                ]
        return InquiryDetail(
            **_summary_fields(inquiry),
            email=inquiry.email,
            content=inquiry.content,
            internal_note=inquiry.internal_note,
            first_viewed_at=inquiry.first_viewed_at,
            completed_at=inquiry.completed_at,
            updated_at=inquiry.updated_at,
            chat_id=inquiry.chat_id,
            trigger_turn_id=inquiry.trigger_turn_id,
            conversation=conversation,
        )


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "문의를 찾을 수 없어요.")
