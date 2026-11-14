"""관리자 문의 관리: 목록, 상태별 건수, 상세(채팅 기록), 읽음·상태·메모 수정.

/api/admin/* 전체에 관리자 토큰이 필요하다. Router는 입력 검증과 Service 호출만 한다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import AdminInquiryServiceDep, require_admin
from app.core.errors import AppError, ErrorCode
from app.repositories.inquiry_repository import InquiryFilter
from app.schemas.admin_common import Page
from app.schemas.admin_inquiry import (
    InquiryCounts,
    InquiryDetail,
    InquiryStatusFilter,
    InquirySummary,
    InquiryUpdate,
)
from app.schemas.error import error_responses
from app.schemas.inquiry import InquiryOrigin

router = APIRouter(
    prefix="/api/admin",
    tags=["문의 관리"],
    dependencies=[Depends(require_admin)],
)

# 기간 조건은 목록과 건수가 같은 문서를 쓴다. 시간대 없는 값은 다른 관리자 API처럼 422로 거절한다
FromQuery = Annotated[
    AwareDatetime | None,
    Query(alias="from", description="포함하는 UTC 경계. 생략하면 전체 기간"),
]
ToQuery = Annotated[
    AwareDatetime | None,
    Query(alias="to", description="포함하지 않는 UTC 경계. 생략하면 전체 기간"),
]


def _period(
    start: datetime | None, end: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if start is not None and end is not None and start >= end:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "from은 to보다 앞이어야 해요.", fields=["from", "to"]
        )
    return start, end


@router.get(
    "/inquiries",
    response_model=Page[InquirySummary],
    responses=error_responses(401, 422, 503),
    summary="문의 목록",
    description=(
        "기간(from/to)을 생략하면 전체 기간. 화면 기본값은 '처리 전 + 전체 기간'으로 둬서 "
        "상단 미확인 배지와 같은 범위를 보여 준다. 기간 옵션은 오늘/7일/30일/전체. "
        "created_at 내림차순·id 내림차순. unresolved=received+in_progress."
    ),
)
async def list_inquiries(
    service: AdminInquiryServiceDep,
    created_from: FromQuery = None,
    created_to: ToQuery = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: InquiryStatusFilter = "unresolved",
    origin: InquiryOrigin | None = None,
    viewed: bool | None = None,
) -> Page[InquirySummary]:
    start, end = _period(created_from, created_to)
    condition = InquiryFilter(
        created_from=start, created_to=end, origin=origin, status=status, viewed=viewed
    )
    return await service.list(condition, page, size)


@router.get(
    "/inquiry-counts",
    response_model=InquiryCounts,
    responses=error_responses(401, 422, 503),
    summary="문의 상태별 건수",
    description=(
        "기간 생략 시 전체 기간. 목록 탭은 목록과 같은 기간·origin으로 호출. "
        "상단 배지는 필터 없이 호출."
    ),
)
async def inquiry_counts(
    service: AdminInquiryServiceDep,
    created_from: FromQuery = None,
    created_to: ToQuery = None,
    origin: InquiryOrigin | None = None,
) -> InquiryCounts:
    start, end = _period(created_from, created_to)
    return await service.counts(InquiryFilter(created_from=start, created_to=end, origin=origin))


@router.get(
    "/inquiries/{id}",
    response_model=InquiryDetail,
    responses=error_responses(401, 404, 422, 503),
    summary="문의 상세·채팅 기록",
    description=(
        "조회로 읽음 상태를 바꾸지 않는다. 채팅 기록(conversation)은 연결된 대화의 turn 중 "
        "finished_at이 경계 turn의 finished_at 이하인 것을 오래된 순으로 준다. 경계 turn은 문의 "
        "접수 순간 서버가 확인한 그 대화의 마지막 저장 turn(완료·실패 모두)이라, 실패한 질문 뒤 "
        "접수한 문의에도 그 질문이 남고 이후 조회가 늘어나지 않는다. 저장된 turn이 없는 대화나 "
        "대화 없는 문의는 conversation=[]. 문의 이후 대화는 chat_id로 질문 로그에서 본다."
    ),
)
async def get_inquiry(id: uuid.UUID, service: AdminInquiryServiceDep) -> InquiryDetail:
    return await service.detail(id)


@router.patch(
    "/inquiries/{id}",
    response_model=InquiryDetail,
    responses=error_responses(401, 404, 422, 503),
    summary="읽음·처리 상태·메모 변경",
    description=(
        "최소 1개 필드. viewed=true는 최초 읽음 시각만 기록. completed 진입 시 완료 시각, "
        "다른 상태로 변경 시 null. 같은 completed 재저장은 시각 유지. 마지막 저장 우선. "
        "내부 메모는 고객 비공개."
    ),
)
async def update_inquiry(
    id: uuid.UUID,
    body: InquiryUpdate,
    service: AdminInquiryServiceDep,
) -> InquiryDetail:
    return await service.update(id, body)
