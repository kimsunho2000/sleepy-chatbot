"""관리자 로그인. 환경변수 계정 1개와 만료가 있는 서명 토큰(JWT)을 쓴다."""

import logging
from datetime import timedelta

from app.core.config import AppSettings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import LoginGuard
from app.core.security import issue_admin_token, read_admin_token, same_secret
from app.schemas.admin import AdminIdentity, TokenRequest, TokenResponse

logger = logging.getLogger(__name__)

LOGIN_FAILED = "아이디 또는 비밀번호가 올바르지 않아요."


class AdminAuthService:
    """DB를 쓰지 않으므로 동기 함수로 둔다."""

    def __init__(self, settings: AppSettings, guard: LoginGuard) -> None:
        self.settings = settings
        self.guard = guard

    def login(self, request: TokenRequest, client_ip_hash: str) -> TokenResponse:
        blocked = self.guard.blocked_for(client_ip_hash)
        if blocked is not None:
            raise AppError(
                ErrorCode.RATE_LIMITED, "로그인 시도가 많아 잠시 막혔어요.", retry_after=blocked
            )
        s = self.settings
        # 아이디와 비밀번호를 모두 비교해 어느 쪽이 틀렸는지 응답 시간으로 드러나지 않게 한다
        username_ok = same_secret(request.username, s.admin_username)
        password_ok = same_secret(
            request.password.get_secret_value(), s.admin_password.get_secret_value()
        )
        if not (username_ok and password_ok):
            self.guard.fail(client_ip_hash)
            # 비밀번호와 토큰은 로그에 남기지 않는다
            logger.info("관리자 로그인 실패")
            raise AppError(ErrorCode.UNAUTHORIZED, LOGIN_FAILED)

        self.guard.succeed(client_ip_hash)
        token, expires_at = issue_admin_token(
            s.admin_username,
            s.admin_display_name,
            s.admin_token_secret.get_secret_value(),
            timedelta(hours=s.admin_token_ttl_hours),
        )
        return TokenResponse(token=token, display_name=s.admin_display_name, expires_at=expires_at)

    def identify(self, token: str | None) -> AdminIdentity:
        claims = (
            read_admin_token(token, self.settings.admin_token_secret.get_secret_value())
            if token
            else None
        )
        # 계정이 하나라 토큰의 사용자가 지금 설정의 관리자인지도 확인한다 (계정을 바꾸면 이전 토큰 무효)
        if claims is None or claims.username != self.settings.admin_username:
            raise AppError(ErrorCode.UNAUTHORIZED, "다시 로그인해 주세요.")
        return AdminIdentity(display_name=claims.display_name, expires_at=claims.expires_at)
