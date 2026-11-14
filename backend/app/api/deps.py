"""Router가 Depends로 받는 설정, DB 세션, Service, 토큰, 클라이언트 IP.

I/O가 없는 의존성도 async def로 둔다. def로 두면 FastAPI가 요청마다 스레드풀로 넘긴다.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppSettings
from app.core.security import hash_ip
from app.schemas.admin import AdminIdentity
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_inquiry_service import AdminInquiryService
from app.services.admin_log_service import AdminLogService
from app.services.chat_service import ChatService
from app.services.inquiry_service import InquiryService

# auto_error=False: 토큰이 없을 때 FastAPI 기본 403 대신 공통 오류 형식(401)으로 답한다
chat_bearer = HTTPBearer(
    scheme_name="ChatBearer",
    description="해당 대화를 만들 때 발급되는 소유권 토큰",
    auto_error=False,
)
admin_bearer = HTTPBearer(
    scheme_name="AdminBearer", description="관리자 로그인으로 받은 토큰", auto_error=False
)


async def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.settings


SettingsDep = Annotated[AppSettings, Depends(get_app_settings)]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def client_ip(request: Request, settings: SettingsDep) -> str:
    """X-Forwarded-For의 맨 오른쪽에서 trusted_proxy_count번째 값. 왼쪽 값은 고객이 위조할 수 있다."""
    count = settings.trusted_proxy_count
    if count > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if len(hops) >= count:
            return hops[-count]
    return request.client.host if request.client else "unknown"


async def client_ip_hash(ip: Annotated[str, Depends(client_ip)], settings: SettingsDep) -> str:
    return hash_ip(ip, settings.ip_hash_secret.get_secret_value())


ClientIpHashDep = Annotated[str, Depends(client_ip_hash)]


def _token(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    return credentials.credentials if credentials else None


async def chat_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(chat_bearer)],
) -> str | None:
    return _token(credentials)


ChatTokenDep = Annotated[str | None, Depends(chat_token)]


async def optional_chat_token(request: Request) -> str | None:
    """토큰이 선택인 API(문의 접수)용. 보안 스킴을 붙이지 않고 Router가 명세에 선택으로 적는다."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


OptionalChatTokenDep = Annotated[str | None, Depends(optional_chat_token)]


async def get_chat_service(
    request: Request, session: SessionDep, settings: SettingsDep
) -> ChatService:
    state = request.app.state
    return ChatService(session, settings, state.limiter, state.rag)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


async def get_inquiry_service(
    request: Request, session: SessionDep, settings: SettingsDep
) -> InquiryService:
    return InquiryService(session, settings, request.app.state.limiter)


InquiryServiceDep = Annotated[InquiryService, Depends(get_inquiry_service)]


async def get_admin_inquiry_service(session: SessionDep) -> AdminInquiryService:
    return AdminInquiryService(session)


AdminInquiryServiceDep = Annotated[AdminInquiryService, Depends(get_admin_inquiry_service)]


async def get_admin_auth_service(request: Request, settings: SettingsDep) -> AdminAuthService:
    return AdminAuthService(settings, request.app.state.login_guard)


AdminAuthServiceDep = Annotated[AdminAuthService, Depends(get_admin_auth_service)]


async def require_admin(
    service: AdminAuthServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_bearer)],
) -> AdminIdentity:
    """/api/admin/* 전체에 붙인다 (로그인 제외)."""
    return service.identify(_token(credentials))


AdminDep = Annotated[AdminIdentity, Depends(require_admin)]


async def get_admin_log_service(session: SessionDep, settings: SettingsDep) -> AdminLogService:
    return AdminLogService(session, settings)


AdminLogServiceDep = Annotated[AdminLogService, Depends(get_admin_log_service)]
