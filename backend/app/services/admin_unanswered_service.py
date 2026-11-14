"""미답변 조회 정책과 응답 조립. FAQ 1순위 묶기는 팀에서 채택한 설계다."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.sql.selectable import CTE

from app.core.errors import AppError, ErrorCode
from app.repositories.admin_unanswered_repository import (
    AdminUnansweredRepository,
    unanswered_rows,
)
from app.schemas.admin_unanswered import (
    GroupDetail,
    GroupPage,
    InquiryLink,
    QuestionVariant,
    TurnPage,
    UnansweredGroup,
    UnansweredTurn,
)


def period(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    for field, value in (("from", start), ("to", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise AppError(ErrorCode.VALIDATION_ERROR, "시간대를 포함해 주세요.", fields=[field])
    end = (end or datetime.now(UTC)).astimezone(UTC)
    start = start.astimezone(UTC) if start is not None else end - timedelta(days=30)
    if start >= end:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "기간의 시작은 끝보다 빨라야 해요.",
            fields=["from", "to"],
        )
    return start, end


def _links(rows: list[dict[str, Any]]) -> list[InquiryLink]:
    return [InquiryLink(id=row["id"], reference_no=row["reference_no"]) for row in rows]


def _group(row: dict[str, Any], links: list[dict[str, Any]]) -> UnansweredGroup:
    return UnansweredGroup(
        **{key: value for key, value in row.items() if key != "source_key"},
        group_key="none" if row["source_key"] is None else row["source_key"],
        inquiries=_links(links),
    )


class AdminUnansweredService:
    def __init__(self, repo: AdminUnansweredRepository) -> None:
        self.repo = repo

    async def _rows(self, start: datetime | None, end: datetime | None) -> CTE:
        start, end = period(start, end)
        rows = unanswered_rows(start, end)
        if await self.repo.has_reserved_key(rows):
            raise AppError(
                ErrorCode.CONFLICT,
                "검색 출처 ID 'none'이 예약된 그룹 키와 충돌해요.",
            )
        return rows

    async def list_groups(
        self, start: datetime | None, end: datetime | None, page: int, size: int
    ) -> GroupPage:
        rows = await self._rows(start, end)
        groups, total = await self.repo.groups(rows, page, size)
        links = await self.repo.inquiry_links(rows, [row["source_key"] for row in groups])
        return GroupPage(
            items=[_group(row, links.get(row["source_key"], [])) for row in groups],
            page=page,
            size=size,
            total_count=total,
        )

    async def get_group(
        self, key: str, start: datetime | None, end: datetime | None, page: int, size: int
    ) -> GroupDetail:
        rows = await self._rows(start, end)
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
            turns=TurnPage(
                items=[
                    UnansweredTurn(
                        turn_id=turn["turn_id"],
                        question=turn["question"],
                        status="completed",
                        mode=turn["mode"],
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
