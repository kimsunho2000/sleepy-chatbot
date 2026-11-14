"""공통 오류 응답 스키마. 실제 응답은 app.core.errors의 핸들러가 만들고, 여기는 OpenAPI 문서용이다."""

import uuid
from typing import Literal

from pydantic import BaseModel

ErrorCodeValue = Literal[
    "validation_error",
    "unauthorized",
    "not_found",
    "conflict",
    "rate_limited",
    "daily_limit_reached",
    "service_busy",
    "ai_unavailable",
    "ai_timeout",
    "db_unavailable",
]


class ErrorBody(BaseModel):
    code: ErrorCodeValue
    message: str
    fields: list[str]


class ErrorResponse(BaseModel):
    error: ErrorBody
    # 실패 turn이 저장된 경우에만 준다 (ai_unavailable, ai_timeout)
    turn_id: uuid.UUID | None = None


def error_responses(*statuses: int) -> dict[int | str, dict]:
    """Router의 responses=에 넣을 오류 응답 문서."""
    descriptions = {
        401: "토큰 없음·만료",
        404: "리소스 없음 또는 대화 소유권 불일치",
        409: "request_id 재사용 시 본문 불일치",
        422: "입력/연결 조건 오류",
        429: "요청 제한 초과. Retry-After 헤더로 남은 초를 준다",
        503: "service_busy, ai_unavailable 또는 db_unavailable",
        504: "답변 제한 시간 초과(ai_timeout). 실패 turn의 turn_id를 준다",
    }
    return {
        status: {"model": ErrorResponse, "description": descriptions[status]} for status in statuses
    }
