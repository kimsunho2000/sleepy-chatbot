"""고객 문의 접수."""

from fastapi import APIRouter, status

from app.api.deps import ClientIpHashDep, InquiryServiceDep, OptionalChatTokenDep
from app.schemas.error import error_responses
from app.schemas.inquiry import InquiryRequest, InquiryResponse

router = APIRouter(prefix="/api/inquiries", tags=["고객 문의"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=InquiryResponse,
    responses=error_responses(401, 404, 409, 422, 429, 503),
    summary="문의 접수 (chat_id를 보내면 그 대화의 토큰이 필요하다)",
    # 대화 없는 직접 문의는 토큰 없이 접수한다. 토큰은 chat_id를 보낼 때만 필요하다
    openapi_extra={"security": [{}, {"ChatBearer": []}]},
)
async def create_inquiry(
    body: InquiryRequest,
    service: InquiryServiceDep,
    token: OptionalChatTokenDep,
    ip_hash: ClientIpHashDep,
) -> InquiryResponse:
    return await service.create(body, token, ip_hash)
