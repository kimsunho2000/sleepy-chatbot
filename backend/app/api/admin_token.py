"""관리자 접근: 로그인(토큰 발급)과 토큰 확인. 로그아웃은 프론트가 토큰을 버리는 것으로 끝난다."""

from fastapi import APIRouter, status

from app.api.deps import AdminAuthServiceDep, AdminDep, ClientIpHashDep
from app.schemas.admin import AdminIdentity, TokenRequest, TokenResponse
from app.schemas.error import error_responses

router = APIRouter(prefix="/api/admin/tokens", tags=["관리자 접근"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    responses=error_responses(401, 422, 429),
    summary="로그인. 실패 이유는 구분하지 않는다",
)
async def create_token(
    body: TokenRequest, service: AdminAuthServiceDep, ip_hash: ClientIpHashDep
) -> TokenResponse:
    return service.login(body, ip_hash)


@router.get(
    "/current",
    response_model=AdminIdentity,
    responses=error_responses(401),
    summary="토큰 확인",
)
async def current_token(admin: AdminDep) -> AdminIdentity:
    return admin
