"""미답변 조회 정책과 응답 조립. FAQ 1순위 묶기는 팀에서 채택한 설계다."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.sql.selectable import CTE

from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import kst_day_start
from app.repositories.admin_unanswered_repository import (
    AdminUnansweredRepository,
    unanswered_rows,
)
from app.schemas.admin_common import LinkedInquiry, Page
from app.schemas.admin_unanswered import (
    GroupDetail,
    QuestionVariant,
    UnansweredGroup,
    UnansweredTurn,
)

DEFAULT_DAYS = 30


def period(
    start: datetime | None, end: datetime | None, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """둘 다 생략하면 한국 날짜로 오늘을 포함한 30일이다(대시보드와 같은 자정 경계).

    from만 주면 to는 오늘 자정 다음 날까지다. 대시보드처럼 from에서 기본 일수를 더하지 않는다.
    """
    for field, value in (("from", start), ("to", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise AppError(ErrorCode.VALIDATION_ERROR, "시간대를 포함해 주세요.", fields=[field])
    end = (end or kst_day_start(now) + timedelta(days=1)).astimezone(UTC)
    start = start.astimezone(UTC) if start is not None else end - timedelta(days=DEFAULT_DAYS)
    if start >= end:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "기간의 시작은 끝보다 빨라야 해요.",
            fields=["from", "to"],
        )
    return start, end


def _links(rows: list[dict[str, Any]]) -> list[LinkedInquiry]:
    return [LinkedInquiry(id=row["id"], reference_no=row["reference_no"]) for row in rows]


def _group(row: dict[str, Any], links: list[dict[str, Any]]) -> UnansweredGroup:
    return UnansweredGroup(
        **{key: value for key, value in row.items() if key != "source_key"},
        group_key="none" if row["source_key"] is None else row["source_key"],
        inquiries=_links(links),
    )


class AdminUnansweredService:
    def __init__(self, repo: AdminUnansweredRepository) -> None:
        self.repo = repo

    @staticmethod
    def _rows(start: datetime | None, end: datetime | None) -> CTE:
        start, end = period(start, end)
        return unanswered_rows(start, end)

    async def list_groups(
        self, start: datetime | None, end: datetime | None, page: int, size: int
    ) -> Page[UnansweredGroup]:
        rows = self._rows(start, end)
        groups, total = await self.repo.groups(rows, page, size)
        links = await self.repo.inquiry_links(rows, [row["source_key"] for row in groups])
        return Page[UnansweredGroup](
            items=[_group(row, links.get(row["source_key"], [])) for row in groups],
            page=page,
            size=size,
            total_count=total,
        )

    async def get_group(
        self, key: str, start: datetime | None, end: datetime | None, page: int, size: int
    ) -> GroupDetail:
        rows = self._rows(start, end)
        groups, _ = await self.repo.groups(rows, 1, 1, key)
        if not groups:
            raise AppError(ErrorCode.NOT_FOUND, "미답변 그룹을 찾을 수 없어요.")
        row = groups[0]
        all_links = await self.repo.inquiry_links(rows, [row["source_key"]])
        links = all_links.get(row["source_key"], [])
        variants, turns = await self.repo.detail(rows, key, page, size)
        return GroupDetail(
            group=_group(row, links),
            variants=[QuestionVariant(**variant) for variant in variants],
            turns=Page[UnansweredTurn](
                items=[
                    UnansweredTurn(
                        turn_id=turn["turn_id"],
                        chat_id=turn["chat_id"],
                        question=turn["question"],
                        status="completed",
                        mode=turn["mode"],
                        latency_ms=turn["latency_ms"],
                        rating=turn["rating"],
                        created_at=turn["created_at"],
                        inquiries=_links(
                            [link for link in links if link["trigger_turn_id"] == turn["turn_id"]]
                        ),
                    )
                    for turn in turns
                ],
                page=page,
                size=size,
                total_count=row["occurrence_count"],
            ),
        )
