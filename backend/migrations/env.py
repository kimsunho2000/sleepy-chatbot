"""Alembic 마이그레이션 실행 환경.

연결 주소는 .env의 DATABASE_URL을 쓴다. 테스트처럼 다른 DB에 적용할 때는
Config에 sqlalchemy.url을 직접 넣는다.
"""

import asyncio
import uuid
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import DatabaseSettings
from app.db.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database() -> tuple[str, dict]:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url, {}
    settings = DatabaseSettings()
    connect_args: dict = {}
    if settings.uses_pgbouncer:
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        }
    return settings.database_url, connect_args


def run_migrations_offline() -> None:
    """DB에 연결하지 않고 SQL만 출력한다 (alembic upgrade head --sql)."""
    url, _ = _database()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url, connect_args = _database()
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
