"""DB 엔진과 세션. 엔진은 앱 시작 때 하나 만들어 app.state에 둔다."""

import uuid

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import AppSettings


def create_engine(settings: AppSettings) -> AsyncEngine:
    connect_args: dict = {}
    if settings.uses_pgbouncer:
        # transaction 모드 pooler는 연결마다 prepared statement를 유지하지 못한다
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        }
    return create_async_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    # 커밋 뒤에도 응답을 만들 때 속성을 다시 읽지 않도록 expire_on_commit=False
    return async_sessionmaker(engine, expire_on_commit=False)
