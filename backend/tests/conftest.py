"""API 테스트 공통 준비.

- DB: 로컬 Docker PostgreSQL의 sleeby_test (docker compose up -d). TEST_DATABASE_URL로 바꿀 수 있다.
- RAG: 실제 OpenAI를 부르지 않는 가짜 구현(FakeRag)을 넣는다.
"""

import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import AppSettings
from app.main import create_app
from app.services.rag_runtime import RagRuntime
from rag.schemas import RagResponse, Source

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://sleeby:sleeby@localhost:5433/sleeby_test"
)
TABLES = "chat, chat_turn, turn_source, feedback, inquiry"
ADMIN_PASSWORD = "test-admin-password"
TITLES = {"Q01": "슬리비는 어떤 제품인가요?", "Q02": "충전은 어떻게 하나요?", "P01": "제품 소개"}


def source(faq_id: str, score: float = 0.8) -> Source:
    return Source(
        faq_id=faq_id, title=TITLES.get(faq_id, faq_id), category="c", score=score, excerpt="e"
    )


def rag_response(**overrides: object) -> RagResponse:
    values: dict = {
        "mode": "answer",
        "answer": "USB-C 케이블로 충전해요.",
        "sources": [source("Q02")],
        "show_contact": False,
        "reason": "Q02에 있음",
        "retrieved_ids": ["Q02", "Q01"],
        "retrieved_scores": [0.8, 0.4],
        "latency_ms": 120.0,
        "prompt_tokens": 100,
        "completion_tokens": 20,
    }
    values.update(overrides)
    return RagResponse(**values)


@dataclass
class FakeRag:
    """aanswer 결과를 테스트가 정한다. respond가 예외를 내면 그대로 올려 보낸다."""

    respond: Callable[[str, list[str]], object] = field(
        default=lambda question, history: rag_response()
    )
    calls: list[tuple[str, list[str]]] = field(default_factory=list)

    async def aretrieve(self, question: str, k: int) -> list[Source]:
        return []

    async def aanswer(self, question: str, history: list[str] | None = None) -> RagResponse:
        self.calls.append((question, list(history or [])))
        result = self.respond(question, list(history or []))
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """테스트 DB를 비우고 Alembic 마이그레이션으로 테이블을 만든다. 마이그레이션 자체도 함께 검증된다."""
    config = Config()
    config.file_config.read(BACKEND_DIR / "alembic.ini", encoding="utf-8")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.attributes["configure_logger"] = False
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
async def db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        await conn.execute(text("ALTER SEQUENCE inquiry_reference_seq RESTART WITH 1001"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def make_settings(**overrides: object) -> AppSettings:
    values: dict = {
        "database_url": TEST_DATABASE_URL,
        "database_pgbouncer": False,
        "admin_username": "admin",
        "admin_password": ADMIN_PASSWORD,
        "admin_display_name": "테스트 관리자",
        "admin_token_secret": "t" * 32,
        "ip_hash_secret": "i" * 16,
        "rag_timeout_seconds": 1.0,
        "cors_origins": ["http://chat.example"],
    }
    values.update(overrides)
    # .env를 읽지 않아 개발 환경 값이 테스트에 섞이지 않는다
    return AppSettings(_env_file=None, **values)


@pytest.fixture
def fake_rag() -> FakeRag:
    return FakeRag()


@pytest.fixture
def settings_overrides() -> dict:
    """테스트가 한도 같은 설정을 바꾸려면 이 fixture를 덮어쓴다."""
    return {}


@pytest.fixture
async def client(
    db: async_sessionmaker[AsyncSession], fake_rag: FakeRag, settings_overrides: dict
) -> AsyncIterator[AsyncClient]:
    runtime = RagRuntime(
        system=fake_rag,
        titles=TITLES,
        history_turns=1,
        config_name="test",
        llm_model="fake-model",
    )
    app = create_app(make_settings(**settings_overrides), rag=runtime)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def new_chat(client: AsyncClient) -> tuple[str, dict[str, str]]:
    response = await client.post("/api/chats")
    assert response.status_code == 201, response.text
    body = response.json()
    return body["chat_id"], {"Authorization": f"Bearer {body['chat_token']}"}


async def ask(
    client: AsyncClient,
    chat_id: str,
    headers: dict[str, str],
    question: str = "충전은 어떻게 하나요?",
    parent_turn_id: str | None = None,
) -> dict:
    response = await client.post(
        f"/api/chats/{chat_id}/turns",
        json={"question": question, "parent_turn_id": parent_turn_id},
        headers=headers,
    )
    return {"status": response.status_code, "body": response.json(), "headers": response.headers}
