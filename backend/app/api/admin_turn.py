"""관리자 질문 로그: 목록과 상세(검색 후보, 답변 근거, 판단 사유, 사용량)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import AdminLogServiceDep, require_admin
from app.repositories.admin_log_repository import TurnFilter
from app.schemas.admin_log import Page, RatingFilter, TurnLogDetail, TurnLogItem, TurnStatus
from app.schemas.chat import Mode
from app.schemas.error import error_responses

router = APIRouter(
    prefix="/api/admin/turns", tags=["관리자 질문 로그"], dependencies=[Depends(require_admin)]
)


@router.get(
    "",
    response_model=Page[TurnLogItem],
    responses=error_responses(401, 422, 503),
    summary="질문 로그 목록. chat_id를 주면 그 대화를 오래된 순으로 준다",
)
async def list_turns(
    service: AdminLogServiceDep,
    period_from: Annotated[
        AwareDatetime | None, Query(alias="from", description="포함. UTC ISO 8601")
    ] = None,
    period_to: Annotated[
        AwareDatetime | None, Query(alias="to", description="미포함. UTC ISO 8601")
    ] = None,
    mode: Mode | None = None,
    status: TurnStatus | None = None,
    rating: Annotated[RatingFilter | None, Query(description="none은 피드백 없음")] = None,
    chat_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[TurnLogItem]:
    filters = TurnFilter(
        period_from=period_from,
        period_to=period_to,
        mode=mode,
        status=status,
        rating=rating,
        chat_id=chat_id,
    )
    return await service.list_turns(filters, page, size)


@router.get(
    "/{turn_id}",
    response_model=TurnLogDetail,
    responses=error_responses(401, 404, 422, 503),
    summary="질문 로그 상세",
)
async def get_turn(turn_id: uuid.UUID, service: AdminLogServiceDep) -> TurnLogDetail:
    return await service.get_turn(turn_id)
