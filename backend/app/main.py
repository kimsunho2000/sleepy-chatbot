"""FastAPI 앱. 실행 (backend/에서): uv run uvicorn app.main:create_app --factory --reload"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_dashboard,
    admin_inquiry,
    admin_token,
    admin_turn,
    admin_unanswered,
    chat,
    inquiry,
)
from app.core.config import AppSettings, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import LoginGuard, SlidingWindowLimiter
from app.db.session import create_engine, create_session_factory
from app.services.rag_runtime import RagRuntime, load_rag_runtime

logger = logging.getLogger(__name__)

DESCRIPTION = """슬리비 챗봇 고객 API와 관리자 API.

- 고객 응답에는 출처를 넣지 않는다. 검색 후보와 답변 근거는 관리자 API에서만 조회한다.
- 시간은 UTC ISO 8601. 오류는 `{error: {code, message, fields}}` 형식이다.
- 요청 제한에 걸리면 `Retry-After` 헤더로 남은 초를 준다.
"""


def create_app(settings: AppSettings | None = None, rag: RagRuntime | None = None) -> FastAPI:
    """테스트는 settings와 가짜 rag를 넣어 만든다."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(app_settings)
        app.state.settings = app_settings
        app.state.session_factory = create_session_factory(engine)
        app.state.limiter = SlidingWindowLimiter()
        app.state.login_guard = LoginGuard(
            app_settings.admin_login_max_failures,
            app_settings.admin_login_lockout_minutes * 60,
        )
        # RAG는 시작할 때 한 번 만든다. 인덱스가 데이터와 맞지 않으면 여기서 실패한다
        app.state.rag = rag or load_rag_runtime(app_settings.rag_config)
        logger.info("RAG 준비 완료: %s", app.state.rag.config_name)
        try:
            yield
        finally:
            app.state.rag.close()
            await engine.dispose()

    app = FastAPI(
        title="Sleeby 챗봇 · 관리자 API",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        # 이 설정이 없으면 브라우저가 프론트에 Retry-After 값을 넘기지 않는다
        expose_headers=["Retry-After"],
    )
    register_error_handlers(app)
    app.include_router(chat.router)
    app.include_router(inquiry.router)
    app.include_router(admin_token.router)
    app.include_router(admin_inquiry.router)
    app.include_router(admin_turn.router)
    app.include_router(admin_dashboard.router)
    app.include_router(admin_unanswered.router)
    return app
