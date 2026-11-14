"""공통 오류 형식 {error: {code, message, fields}, turn_id?}과 예외 핸들러."""

import logging
import uuid
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    SERVICE_BUSY = "service_busy"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_TIMEOUT = "ai_timeout"
    DB_UNAVAILABLE = "db_unavailable"


STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.DAILY_LIMIT_REACHED: 429,
    ErrorCode.SERVICE_BUSY: 503,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.AI_TIMEOUT: 504,
    ErrorCode.DB_UNAVAILABLE: 503,
}

DEFAULT_MESSAGE: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "입력값을 확인해 주세요.",
    ErrorCode.UNAUTHORIZED: "인증이 필요하거나 만료됐어요.",
    ErrorCode.NOT_FOUND: "찾을 수 없어요.",
    ErrorCode.CONFLICT: "같은 요청 번호로 다른 내용이 접수됐어요.",
    ErrorCode.RATE_LIMITED: "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.",
    ErrorCode.DAILY_LIMIT_REACHED: "오늘 이용 가능한 횟수를 넘었어요.",
    ErrorCode.SERVICE_BUSY: "지금은 답변이 어려워요.",
    ErrorCode.AI_UNAVAILABLE: "일시적으로 답변이 어려워요.",
    ErrorCode.AI_TIMEOUT: "답변이 늦어지고 있어요.",
    ErrorCode.DB_UNAVAILABLE: "일시적인 오류예요.",
}


class AppError(Exception):
    """Service가 내는 업무 오류. 공통 핸들러가 오류 형식으로 바꾼다."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        fields: list[str] | None = None,
        retry_after: int | None = None,
        turn_id: uuid.UUID | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGE[code]
        self.fields = fields or []
        self.retry_after = retry_after
        self.turn_id = turn_id
        super().__init__(self.message)


def error_response(
    code: ErrorCode,
    message: str | None = None,
    *,
    fields: list[str] | None = None,
    retry_after: int | None = None,
    turn_id: uuid.UUID | None = None,
) -> JSONResponse:
    body: dict = {
        "error": {
            "code": code.value,
            "message": message or DEFAULT_MESSAGE[code],
            "fields": fields or [],
        }
    }
    if turn_id is not None:
        body["turn_id"] = str(turn_id)
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(body, status_code=STATUS_BY_CODE[code], headers=headers)


def _field_name(loc: tuple) -> str:
    # ("body", "question") → "question". 경로·헤더 값도 이름만 남긴다
    parts = [str(p) for p in loc[1:]] if len(loc) > 1 else [str(p) for p in loc]
    return ".".join(parts)


async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(
        exc.code,
        exc.message,
        fields=exc.fields,
        retry_after=exc.retry_after,
        turn_id=exc.turn_id,
    )


async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted({_field_name(tuple(e.get("loc", ()))) for e in exc.errors()})
    return error_response(ErrorCode.VALIDATION_ERROR, fields=fields)


async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # 없는 경로와 허용하지 않는 메서드는 모두 "없음"으로 본다
    if exc.status_code in (404, 405):
        return error_response(ErrorCode.NOT_FOUND)
    if exc.status_code == 401:
        return error_response(ErrorCode.UNAUTHORIZED)
    return error_response(ErrorCode.VALIDATION_ERROR, str(exc.detail))


async def handle_db_error(_: Request, exc: Exception) -> JSONResponse:
    # 연결 문자열이나 비밀번호가 로그에 남지 않도록 예외 종류만 기록한다
    logger.error("DB 연결 실패: %s", type(exc).__name__)
    return error_response(ErrorCode.DB_UNAVAILABLE)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    # asyncpg는 연결 실패(거부, DNS, 시간 초과, 여러 주소 모두 실패)를 감싸지 않고 OSError로 올린다.
    # RAG 오류는 Service가 먼저 잡으므로 여기까지 오는 OSError는 DB 연결 문제다
    for exc_type in (OperationalError, InterfaceError, PoolTimeoutError, OSError):
        app.add_exception_handler(exc_type, handle_db_error)
