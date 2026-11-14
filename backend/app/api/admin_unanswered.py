"""관리자 미답변 조회. FAQ 1순위 그룹화는 팀에서 채택한 설계 계약이다."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminDep, SessionDep
from app.repositories.admin_unanswered_repository import AdminUnansweredRepository
from app.schemas.admin_unanswered import GroupDetail, GroupPage
from app.schemas.error import error_responses
from app.services.admin_unanswered_service import AdminUnansweredService

router = APIRouter(prefix="/api/admin/unanswered-groups", tags=["관리자 미답변"])


async def get_service(session: SessionDep) -> AdminUnansweredService:
    return AdminUnansweredService(AdminUnansweredRepository(session))


ServiceDep = Annotated[AdminUnansweredService, Depends(get_service)]
Start = Annotated[datetime | None, Query(alias="from")]
End = Annotated[datetime | None, Query(alias="to")]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=GroupPage, responses=error_responses(401, 409, 422, 503))
async def list_groups(
    admin: AdminDep,
    service: ServiceDep,
    start: Start = None,
    end: End = None,
    page: Page = 1,
    size: Size = 20,
) -> GroupPage:
    return await service.list_groups(start, end, page, size)


@router.get(
    "/{group_key}",
    response_model=GroupDetail,
    responses=error_responses(401, 404, 409, 422, 503),
)
async def get_group(
    group_key: str,
    admin: AdminDep,
    service: ServiceDep,
    start: Start = None,
    end: End = None,
    page: Page = 1,
    size: Size = 20,
) -> GroupDetail:
    return await service.get_group(group_key, start, end, page, size)
