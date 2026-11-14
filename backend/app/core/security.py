"""대화 토큰, 관리자 토큰(JWT), IP 해시."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

ADMIN_TOKEN_ALGORITHM = "HS256"


# 대화 토큰은 난수로 발급하고 DB에는 해시만 둔다
def new_chat_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


# IP는 원본 대신 서버 비밀값으로 만든 해시만 저장한다
def hash_ip(ip: str, secret: str) -> str:
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def same_secret(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())


@dataclass(frozen=True)
class AdminClaims:
    username: str
    display_name: str
    expires_at: datetime


def issue_admin_token(
    username: str, display_name: str, secret: str, ttl: timedelta, now: datetime | None = None
) -> tuple[str, datetime]:
    issued = now or datetime.now(UTC)
    expires = issued + ttl
    payload = {"sub": username, "name": display_name, "iat": issued, "exp": expires}
    return jwt.encode(payload, secret, algorithm=ADMIN_TOKEN_ALGORITHM), expires


def read_admin_token(token: str, secret: str) -> AdminClaims | None:
    """서명이 맞고 만료 전이면 내용을, 아니면 None을 돌려준다."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ADMIN_TOKEN_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    return AdminClaims(
        username=payload["sub"],
        display_name=payload.get("name", ""),
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )
