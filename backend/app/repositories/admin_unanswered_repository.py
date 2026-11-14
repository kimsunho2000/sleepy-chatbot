"""미답변 조회 전용 SQL. 저장·수정이나 현재 FAQ 데이터 접근은 하지 않는다."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import CTE

from app.db.models import ChatTurn, Feedback, Inquiry, TurnSource


def unanswered_rows(start: datetime, end: datetime) -> CTE:
    """검색 1순위 그룹화는 팀에서 채택한 설계 계약이다.

    null(후보 없음)과 실제 source_id='none'은 내부에서 구분한다.
    외부 키 충돌은 Service가 감지하여 모호한 결과를 반환하지 않는다.
    """
    return (
        select(
            ChatTurn.id.label("turn_id"),
            ChatTurn.question,
            ChatTurn.mode,
            ChatTurn.created_at,
            Feedback.rating,
            TurnSource.source_id.label("source_key"),
            TurnSource.title.label("source_title"),
        )
        .outerjoin(Feedback, Feedback.turn_id == ChatTurn.id)
        .outerjoin(
            TurnSource,
            and_(
                TurnSource.turn_id == ChatTurn.id,
                TurnSource.kind == "retrieved",
                TurnSource.rank == 1,
            ),
        )
        .where(
            ChatTurn.status == "completed",
            or_(ChatTurn.mode.in_(("unknown", "partial")), Feedback.rating == "down"),
            ChatTurn.created_at >= start,
            ChatTurn.created_at < end,
        )
        .cte("unanswered")
    )


class AdminUnansweredRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_reserved_key(self, rows: CTE) -> bool:
        return bool(
            await self.session.scalar(
                select(select(rows.c.turn_id).where(rows.c.source_key == "none").exists())
            )
        )

    async def groups(
        self, rows: CTE, page: int, size: int, key: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        ranked = select(
            rows,
            func.row_number()
            .over(
                partition_by=rows.c.source_key,
                order_by=(rows.c.created_at.desc(), rows.c.turn_id.asc()),
            )
            .label("position"),
        ).cte("ranked")
        r = ranked.c
        grouped = select(
            r.source_key,
            func.max(case((r.position == 1, r.source_title))).label("source_title"),
            func.max(case((r.position == 1, r.question))).label("representative_question"),
            func.count().label("occurrence_count"),
            func.count().filter(r.mode == "unknown").label("unknown_count"),
            func.count().filter(r.mode == "partial").label("partial_count"),
            func.count().filter(r.rating == "down").label("downvote_count"),
            func.max(r.created_at).label("last_seen_at"),
        ).group_by(r.source_key)
        if key is not None:
            condition = r.source_key.is_(None) if key == "none" else r.source_key == key
            grouped = grouped.where(condition)
        groups = grouped.cte("groups")
        total = await self.session.scalar(select(func.count()).select_from(groups))
        result = await self.session.execute(
            select(groups)
            .order_by(
                groups.c.occurrence_count.desc(),
                groups.c.last_seen_at.desc(),
                groups.c.source_key.asc().nulls_last(),
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        return [dict(row) for row in result.mappings()], int(total or 0)

    async def inquiry_links(
        self, rows: CTE, keys: list[str | None]
    ) -> dict[str | None, list[dict[str, Any]]]:
        if not keys:
            return {}
        condition = rows.c.source_key.in_([key for key in keys if key is not None])
        if None in keys:
            condition = or_(condition, rows.c.source_key.is_(None))
        result = await self.session.execute(
            select(rows.c.source_key, Inquiry.id, Inquiry.reference_no, Inquiry.trigger_turn_id)
            .join(Inquiry, Inquiry.trigger_turn_id == rows.c.turn_id)
            .where(condition)
            .order_by(Inquiry.id)
        )
        links: dict[str | None, list[dict[str, Any]]] = {}
        for row in result.mappings():
            links.setdefault(row["source_key"], []).append(dict(row))
        return links

    async def detail(
        self, rows: CTE, key: str, page: int, size: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        condition = rows.c.source_key.is_(None) if key == "none" else rows.c.source_key == key
        variants = await self.session.execute(
            select(rows.c.question, func.count().label("count"))
            .where(condition)
            .group_by(rows.c.question)
            .order_by(func.count().desc(), rows.c.question.asc())
        )
        turns = await self.session.execute(
            select(rows)
            .where(condition)
            .order_by(rows.c.created_at.desc(), rows.c.turn_id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return (
            [dict(row) for row in variants.mappings()],
            [dict(row) for row in turns.mappings()],
        )
