"""여러 Service가 함께 쓰는 대화 토큰 확인과 분 단위 요청 제한."""

import uuid

from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import token_matches
from app.db.models import Chat
from app.repositories.chat_repository import ChatRepository


async def authorize_chat(repo: ChatRepository, chat_id: uuid.UUID, token: str | None) -> Chat:
    """대화 토큰 확인. 대화 ID만 알아서는 권한이 없다."""
    if not token:
        raise AppError(ErrorCode.UNAUTHORIZED, "대화 토큰이 필요해요.")
    chat = await repo.get_chat(chat_id)
    # 없는 대화와 남의 대화를 구별하지 않는다
    if chat is None or not token_matches(token, chat.token_hash):
        raise AppError(ErrorCode.NOT_FOUND, "대화를 찾을 수 없어요.")
    return chat


def enforce_limit(
    limiter: SlidingWindowLimiter,
    key: str,
    limit: int,
    window: int,
    request_key: str | None = None,
) -> None:
    retry_after = limiter.hit(key, limit, window, request_key)
    if retry_after is not None:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after=retry_after)
