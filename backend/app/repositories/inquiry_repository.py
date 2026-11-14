"""문의 저장소."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatTurn, Inquiry, TurnSource

# "처리 전"으로 묶는 상태
UNRESOLVED_STATUSES = ("received", "in_progress")


@dataclass(frozen=True)
class InquiryFilter:
    """목록과 건수가 같은 조건을 쓰도록 한 곳에 모은다. 기간은 from 포함, to 미포함이다."""

    created_from: datetime | None = None
    created_to: datetime | None = None
    origin: str | None = None
    # 상태 조건은 목록에만 쓴다. 건수는 상태별로 나눠 세므로 None으로 둔다
    status: str | None = None
    viewed: bool | None = None

    def conditions(self) -> list[ColumnElement[bool]]:
        found: list[ColumnElement[bool]] = []
        if self.created_from is not None:
            found.append(Inquiry.created_at >= self.created_from)
        if self.created_to is not None:
            found.append(Inquiry.created_at < self.created_to)
        if self.origin is not None:
            found.append(Inquiry.origin == self.origin)
        if self.status == "unresolved":
            found.append(Inquiry.status.in_(UNRESOLVED_STATUSES))
        elif self.status not in (None, "all"):
            found.append(Inquiry.status == self.status)
        if self.viewed is True:
            found.append(Inquiry.first_viewed_at.is_not(None))
        elif self.viewed is False:
            found.append(Inquiry.first_viewed_at.is_(None))
        return found


@dataclass(frozen=True)
class StatusCounts:
    received: int
    in_progress: int
    completed: int
    unread: int
    total: int


class InquiryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_request_id(self, request_id: uuid.UUID) -> Inquiry | None:
        return await self.session.scalar(select(Inquiry).where(Inquiry.request_id == request_id))

    async def add(self, inquiry: Inquiry) -> Inquiry:
        """저장하고 DB 시퀀스로 채번한 reference_no를 함께 돌려받는다."""
        self.session.add(inquiry)
        await self.session.flush()
        return inquiry

    # ----- 관리자 조회 -----

    async def list_inquiries(
        self, condition: InquiryFilter, page: int, size: int
    ) -> tuple[list[Inquiry], int]:
        """최신순(created_at, id 내림차순). 같은 시각이어도 쪽 사이에 순서가 흔들리지 않는다."""
        where = condition.conditions()
        total = await self.session.scalar(select(func.count()).select_from(Inquiry).where(*where))
        query = (
            select(Inquiry)
            .where(*where)
            .order_by(Inquiry.created_at.desc(), Inquiry.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await self.session.scalars(query)).all()
        return list(rows), total or 0

    async def count_by_status(self, condition: InquiryFilter) -> StatusCounts:
        """한 번의 조회로 상태별·미확인·전체를 센다. 목록과 같은 기간·origin 조건을 쓴다."""
        query = select(
            func.count().filter(Inquiry.status == "received"),
            func.count().filter(Inquiry.status == "in_progress"),
            func.count().filter(Inquiry.status == "completed"),
            func.count().filter(Inquiry.first_viewed_at.is_(None)),
            func.count(),
        ).where(*condition.conditions())
        row = (await self.session.execute(query)).one()
        return StatusCounts(*row)

    async def get(self, inquiry_id: uuid.UUID, *, for_update: bool = False) -> Inquiry | None:
        """for_update면 행을 잠가, 동시에 온 수정(예: 읽음 처리 두 번)이 한 줄로 처리된다."""
        query = select(Inquiry).where(Inquiry.id == inquiry_id)
        if for_update:
            # populate_existing: 잠금을 기다리는 동안 다른 수정이 끝났다면 그 값을 다시 읽는다
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(query)

    async def boundary_finished_at(self, turn_id: uuid.UUID) -> datetime | None:
        return await self.session.scalar(select(ChatTurn.finished_at).where(ChatTurn.id == turn_id))

    async def conversation_turns(
        self, chat_id: uuid.UUID, until: datetime
    ) -> list[tuple[ChatTurn, list[TurnSource]]]:
        """경계 시각까지 저장된 turn(완료·실패 모두)을 오래된 순으로, 출처와 함께 돌려준다."""
        turns = (
            await self.session.scalars(
                select(ChatTurn)
                .where(ChatTurn.chat_id == chat_id, ChatTurn.finished_at <= until)
                # 완료 시각은 DB 시계(마이크로초)라 서버 시계가 거칠어도 순서가 정해진다
                .order_by(ChatTurn.finished_at, ChatTurn.created_at, ChatTurn.id)
            )
        ).all()
        if not turns:
            return []
        sources = (
            await self.session.scalars(
                select(TurnSource)
                .where(TurnSource.turn_id.in_([turn.id for turn in turns]))
                .order_by(TurnSource.turn_id, TurnSource.kind, TurnSource.rank)
            )
        ).all()
        by_turn: dict[uuid.UUID, list[TurnSource]] = {turn.id: [] for turn in turns}
        for source in sources:
            by_turn[source.turn_id].append(source)
        return [(turn, by_turn[turn.id]) for turn in turns]
