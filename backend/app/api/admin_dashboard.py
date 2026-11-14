"""관리자 대시보드: 질문 수, 응답 시간, 불확실 답변·👍 비율, 예상 비용, 일별 질문 수, 많이 참고된 FAQ."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import AdminLogServiceDep, require_admin
from app.schemas.admin_log import DashboardResponse
from app.schemas.error import error_responses

router = APIRouter(
    prefix="/api/admin/dashboard", tags=["관리자 대시보드"], dependencies=[Depends(require_admin)]
)


@router.get(
    "",
    response_model=DashboardResponse,
    responses=error_responses(401, 422, 503),
    summary="대시보드. 기간을 생략하면 한국 날짜로 오늘 포함 7일",
)
async def get_dashboard(
    service: AdminLogServiceDep,
    period_from: Annotated[
        AwareDatetime | None, Query(alias="from", description="포함. UTC ISO 8601")
    ] = None,
    period_to: Annotated[
        AwareDatetime | None, Query(alias="to", description="미포함. UTC ISO 8601")
    ] = None,
) -> DashboardResponse:
    return await service.dashboard(period_from, period_to)
