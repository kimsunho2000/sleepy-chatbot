"""관리자 질문 로그와 대시보드: 필터 검증, 예상 비용 계산, 통계."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppSettings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import KST, kst_day_start
from app.db.models import TurnSource
from app.repositories.admin_log_repository import AdminLogRepository, TurnFilter
from app.schemas.admin_log import (
    DailyCount,
    DashboardResponse,
    FailedByReason,
    LinkedInquiry,
    ModeCounts,
    Page,
    SourceItem,
    TopSource,
    TurnLogDetail,
    TurnLogItem,
)
from app.schemas.chat import FeedbackResponse

DASHBOARD_DEFAULT_DAYS = 7
# 일별 목록이 지나치게 길어지지 않도록 한 번에 볼 수 있는 기간을 제한한다
DASHBOARD_MAX_DAYS = 366
TOP_SOURCE_LIMIT = 5
TOKENS_PER_PRICE_UNIT = 1_000_000
# 불확실 답변 비율의 분모. 인사·범위 밖 질문은 뺀다 (ADMIN.md 팀 확인 필요 4번 초기안)
UNCERTAIN_MODES = ("partial", "unknown")
PRODUCT_MODES = ("answer", "partial", "unknown")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _check_period(period_from: datetime | None, period_to: datetime | None) -> None:
    if period_from is not None and period_to is not None and period_from >= period_to:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "기간의 시작이 끝보다 앞서야 해요.", fields=["from", "to"]
        )


def _sources(rows: list[TurnSource], kind: str) -> list[SourceItem]:
    return [
        SourceItem(rank=row.rank, source_id=row.source_id, title=row.title, score=row.score)
        for row in rows
        if row.kind == kind
    ]


class AdminLogService:
    def __init__(self, session: AsyncSession, settings: AppSettings) -> None:
        self.repo = AdminLogRepository(session)
        self.settings = settings

    def estimate_cost(
        self, prompt_tokens: int | None, completion_tokens: int | None
    ) -> float | None:
        """토큰 × 설정 단가. 단가를 정하지 않았거나 토큰이 기록되지 않았으면 null이다."""
        input_price = self.settings.llm_input_price_per_1m_tokens
        output_price = self.settings.llm_output_price_per_1m_tokens
        if input_price is None or output_price is None:
            return None
        if prompt_tokens is None or completion_tokens is None:
            return None
        return (
            prompt_tokens * input_price + completion_tokens * output_price
        ) / TOKENS_PER_PRICE_UNIT

    # ---- 질문 로그 ----

    async def list_turns(self, filters: TurnFilter, page: int, size: int) -> Page[TurnLogItem]:
        _check_period(filters.period_from, filters.period_to)
        rows, total = await self.repo.list_turns(filters, (page - 1) * size, size)
        items = [
            TurnLogItem(
                turn_id=turn.id,
                chat_id=turn.chat_id,
                question=turn.question,
                status=turn.status,
                mode=turn.mode,
                latency_ms=turn.latency_ms,
                rating=rating,
                created_at=turn.created_at,
            )
            for turn, rating in rows
        ]
        return Page[TurnLogItem](items=items, page=page, size=size, total_count=total)

    async def get_turn(self, turn_id: uuid.UUID) -> TurnLogDetail:
        turn = await self.repo.get_turn(turn_id)
        if turn is None:
            raise AppError(ErrorCode.NOT_FOUND, "질문 로그를 찾을 수 없어요.")
        sources = await self.repo.get_sources(turn.id)
        feedback = await self.repo.get_feedback(turn.id)
        inquiries = await self.repo.linked_inquiries(turn.id)
        return TurnLogDetail(
            turn_id=turn.id,
            chat_id=turn.chat_id,
            parent_turn_id=turn.parent_turn_id,
            question=turn.question,
            status=turn.status,
            mode=turn.mode,
            answer=turn.answer,
            show_contact=turn.show_contact,
            reason=turn.reason,
            error_code=turn.error_code,
            retrieved_sources=_sources(sources, "retrieved"),
            cited_sources=_sources(sources, "cited"),
            latency_ms=turn.latency_ms,
            prompt_tokens=turn.prompt_tokens,
            completion_tokens=turn.completion_tokens,
            estimated_cost_usd=self.estimate_cost(turn.prompt_tokens, turn.completion_tokens),
            llm_model=turn.llm_model,
            config_name=turn.config_name,
            feedback=(
                FeedbackResponse(
                    rating=feedback.rating, reason=feedback.reason, updated_at=feedback.updated_at
                )
                if feedback
                else None
            ),
            inquiries=[LinkedInquiry(id=i, reference_no=no) for i, no in inquiries],
            created_at=turn.created_at,
            finished_at=turn.finished_at,
        )

    # ---- 대시보드 ----

    def dashboard_period(
        self, period_from: datetime | None, period_to: datetime | None, now: datetime | None = None
    ) -> tuple[datetime, datetime]:
        """생략하면 한국 날짜로 오늘을 포함한 7일이다. 한쪽만 주면 다른 쪽을 7일 간격으로 채운다."""
        _check_period(period_from, period_to)
        if period_to is None:
            if period_from is not None:
                period_to = period_from + timedelta(days=DASHBOARD_DEFAULT_DAYS)
            else:
                period_to = kst_day_start(now) + timedelta(days=1)
        if period_from is None:
            period_from = period_to - timedelta(days=DASHBOARD_DEFAULT_DAYS)
        if period_to - period_from > timedelta(days=DASHBOARD_MAX_DAYS):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"대시보드 기간은 최대 {DASHBOARD_MAX_DAYS}일이에요.",
                fields=["from", "to"],
            )
        return period_from.astimezone(UTC), period_to.astimezone(UTC)

    async def dashboard(
        self, period_from: datetime | None, period_to: datetime | None
    ) -> DashboardResponse:
        start, end = self.dashboard_period(period_from, period_to)

        mode_counts = ModeCounts()
        failed_by_reason = FailedByReason()
        question_count = 0
        for row in await self.repo.turn_summary(start, end):
            question_count += row.count
            if row.status == "completed" and row.mode in ModeCounts.model_fields:
                setattr(mode_counts, row.mode, getattr(mode_counts, row.mode) + row.count)
            elif row.status == "failed" and row.error_code in FailedByReason.model_fields:
                field = row.error_code
                setattr(failed_by_reason, field, getattr(failed_by_reason, field) + row.count)
        failed_count = sum(failed_by_reason.model_dump().values())

        modes = mode_counts.model_dump()
        uncertain_ratio = _ratio(
            sum(modes[m] for m in UNCERTAIN_MODES), sum(modes[m] for m in PRODUCT_MODES)
        )

        usage = await self.repo.usage_summary(start, end)
        # 토큰이 기록된 turn이 없으면 $0이 아니라 값 없음이다
        total_cost = (
            self.estimate_cost(usage.prompt_tokens, usage.completion_tokens)
            if usage.priced_turn_count
            else None
        )
        average_cost = total_cost / usage.priced_turn_count if total_cost is not None else None

        ratings = await self.repo.feedback_counts(start, end)
        feedback_count = ratings.get("up", 0) + ratings.get("down", 0)
        unresolved, unread = await self.repo.inquiry_counts()
        daily = await self.repo.daily_counts(start, end)
        top = await self.repo.top_cited_sources(start, end, TOP_SOURCE_LIMIT)

        return DashboardResponse(
            period_from=start,
            period_to=end,
            question_count=question_count,
            mode_counts=mode_counts,
            failed_count=failed_count,
            failed_by_reason=failed_by_reason,
            average_latency_ms=usage.average_latency_ms,
            uncertain_ratio=uncertain_ratio,
            feedback_count=feedback_count,
            positive_feedback_ratio=_ratio(ratings.get("up", 0), feedback_count),
            estimated_cost_usd=total_cost,
            average_cost_usd=average_cost,
            unresolved_inquiry_count=unresolved,
            unread_inquiry_count=unread,
            daily_questions=[
                DailyCount(date=day, count=daily.get(day, 0)) for day in _kst_days(start, end)
            ],
            top_sources=[
                TopSource(source_id=source_id, title=title, count=count)
                for source_id, title, count in top
            ],
        )


def _kst_days(start: datetime, end: datetime) -> list[date]:
    """기간에 걸치는 한국 날짜 전부. 질문이 없는 날도 0으로 채우기 위해 쓴다."""
    first = start.astimezone(KST).date()
    # to는 미포함이라 바로 앞 순간의 날짜가 마지막 날이다
    last = (end - timedelta(microseconds=1)).astimezone(KST).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
