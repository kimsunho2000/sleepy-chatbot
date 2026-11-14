"""관리자 질문 로그·대시보드 조회. 읽기 전용이고 업무 데이터를 바꾸지 않는다."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Date, Interval, Select, cast, func, literal, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import KST
from app.db.models import ChatTurn, Feedback, Inquiry, TurnSource
from app.repositories.inquiry_criteria import unread_inquiry, unresolved_inquiry

# 한국 날짜 경계. 한국은 서머타임이 없어 고정 오프셋(+9시간)으로 충분하고,
# DB에 시간대 데이터가 없어도 하루 한도(kst_day_start)와 같은 기준으로 날짜를 나눈다
KST_OFFSET = KST.utcoffset(None)


@dataclass(frozen=True)
class TurnFilter:
    period_from: datetime | None = None
    period_to: datetime | None = None
    mode: str | None = None
    status: str | None = None
    # up | down | none(피드백 없음)
    rating: str | None = None
    chat_id: uuid.UUID | None = None


@dataclass(frozen=True)
class TurnSummary:
    status: str
    mode: str | None
    error_code: str | None
    count: int


@dataclass(frozen=True)
class UsageSummary:
    average_latency_ms: float | None
    # 토큰이 둘 다 기록된 turn만 센다
    priced_turn_count: int
    prompt_tokens: int
    completion_tokens: int


def _in_period(query: Select, period_from: datetime, period_to: datetime) -> Select:
    return query.where(ChatTurn.created_at >= period_from, ChatTurn.created_at < period_to)


class AdminLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 질문 로그 ----

    async def list_turns(
        self, filters: TurnFilter, offset: int, limit: int
    ) -> tuple[list[tuple[ChatTurn, str | None]], int]:
        query = select(ChatTurn, Feedback.rating).outerjoin(
            Feedback, Feedback.turn_id == ChatTurn.id
        )
        if filters.period_from is not None:
            query = query.where(ChatTurn.created_at >= filters.period_from)
        if filters.period_to is not None:
            query = query.where(ChatTurn.created_at < filters.period_to)
        if filters.mode is not None:
            query = query.where(ChatTurn.mode == filters.mode)
        if filters.status is not None:
            query = query.where(ChatTurn.status == filters.status)
        if filters.rating == "none":
            query = query.where(Feedback.turn_id.is_(None))
        elif filters.rating is not None:
            query = query.where(Feedback.rating == filters.rating)
        if filters.chat_id is not None:
            query = query.where(ChatTurn.chat_id == filters.chat_id)

        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        # 한 대화를 이어 볼 때는 오래된 순, 그 밖에는 최신순
        if filters.chat_id is not None:
            order = (ChatTurn.created_at.asc(), ChatTurn.id.asc())
        else:
            order = (ChatTurn.created_at.desc(), ChatTurn.id.desc())
        rows = (
            await self.session.execute(query.order_by(*order).offset(offset).limit(limit))
        ).all()
        return [(row[0], row[1]) for row in rows], total or 0

    async def get_turn(self, turn_id: uuid.UUID) -> ChatTurn | None:
        return await self.session.get(ChatTurn, turn_id)

    async def get_sources(self, turn_id: uuid.UUID) -> list[TurnSource]:
        query = (
            select(TurnSource)
            .where(TurnSource.turn_id == turn_id)
            .order_by(TurnSource.kind, TurnSource.rank)
        )
        return list((await self.session.scalars(query)).all())

    async def get_feedback(self, turn_id: uuid.UUID) -> Feedback | None:
        return await self.session.get(Feedback, turn_id)

    async def linked_inquiries(self, turn_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        """이 turn을 trigger로 접수된 문의. 문의 테이블은 읽기만 한다."""
        query = (
            select(Inquiry.id, Inquiry.reference_no)
            .where(Inquiry.trigger_turn_id == turn_id)
            .order_by(Inquiry.created_at)
        )
        return [(row.id, row.reference_no) for row in (await self.session.execute(query)).all()]

    # ---- 대시보드 ----

    async def turn_summary(self, period_from: datetime, period_to: datetime) -> list[TurnSummary]:
        query = _in_period(
            select(ChatTurn.status, ChatTurn.mode, ChatTurn.error_code, func.count()),
            period_from,
            period_to,
        ).group_by(ChatTurn.status, ChatTurn.mode, ChatTurn.error_code)
        rows = (await self.session.execute(query)).all()
        return [TurnSummary(row[0], row[1], row[2], row[3]) for row in rows]

    async def usage_summary(self, period_from: datetime, period_to: datetime) -> UsageSummary:
        priced = ChatTurn.prompt_tokens.is_not(None) & ChatTurn.completion_tokens.is_not(None)
        query = _in_period(
            select(
                func.avg(ChatTurn.latency_ms).filter(ChatTurn.status == "completed"),
                func.count().filter(priced),
                func.coalesce(func.sum(ChatTurn.prompt_tokens).filter(priced), 0),
                func.coalesce(func.sum(ChatTurn.completion_tokens).filter(priced), 0),
            ),
            period_from,
            period_to,
        )
        row = (await self.session.execute(query)).one()
        average = float(row[0]) if row[0] is not None else None
        return UsageSummary(average, row[1], int(row[2]), int(row[3]))

    async def feedback_counts(self, period_from: datetime, period_to: datetime) -> dict[str, int]:
        """기간 안에 생성된 turn의 현재 평가 수. 평가가 바뀌면 지난 기간 숫자도 바뀐다."""
        query = _in_period(
            select(Feedback.rating, func.count()).join(ChatTurn, ChatTurn.id == Feedback.turn_id),
            period_from,
            period_to,
        ).group_by(Feedback.rating)
        return {row[0]: row[1] for row in (await self.session.execute(query)).all()}

    async def daily_counts(self, period_from: datetime, period_to: datetime) -> dict[date, int]:
        day = cast(func.timezone(literal(KST_OFFSET, Interval), ChatTurn.created_at), Date)
        query = _in_period(select(day, func.count()), period_from, period_to).group_by(day)
        return {row[0]: row[1] for row in (await self.session.execute(query)).all()}

    async def top_cited_sources(
        self, period_from: datetime, period_to: datetime, limit: int
    ) -> list[tuple[str, str | None, int]]:
        """답변 근거로 많이 쓰인 FAQ. 저장할 때 한 turn에서 같은 FAQ를 합쳐 두었으므로 행 수가 답변 수다."""
        count = func.count().label("count")
        query = (
            _in_period(
                select(TurnSource.source_id, count).join(
                    ChatTurn, ChatTurn.id == TurnSource.turn_id
                ),
                period_from,
                period_to,
            )
            .where(TurnSource.kind == "cited")
            .group_by(TurnSource.source_id)
            .order_by(count.desc(), TurnSource.source_id)
            .limit(limit)
        )
        counted = (await self.session.execute(query)).all()
        if not counted:
            return []
        titles = await self._latest_titles([row[0] for row in counted])
        return [(row[0], titles.get(row[0]), row[1]) for row in counted]

    async def _latest_titles(self, source_ids: list[str]) -> dict[str, str]:
        """FAQ 문구가 바뀌었을 수 있으니 가장 최근에 저장된 제목을 쓴다."""
        query = (
            select(TurnSource.source_id, TurnSource.title)
            .join(ChatTurn, ChatTurn.id == TurnSource.turn_id)
            .where(TurnSource.source_id.in_(source_ids), TurnSource.title.is_not(None))
            .order_by(TurnSource.source_id, ChatTurn.created_at.desc())
            .ext(distinct_on(TurnSource.source_id))
        )
        return {row[0]: row[1] for row in (await self.session.execute(query)).all()}

    async def inquiry_counts(self) -> tuple[int, int]:
        """(미처리, 미확인). 기간과 무관한 전체 문의 수다."""
        query = select(
            func.count().filter(unresolved_inquiry()),
            func.count().filter(unread_inquiry()),
        ).select_from(Inquiry)
        row = (await self.session.execute(query)).one()
        return row[0], row[1]
