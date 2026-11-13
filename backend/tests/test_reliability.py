"""장애·동시 요청·IP 처리: 검증에서 나온 수정 사항을 지키는 테스트."""

import asyncio

import openai
import pytest
from httpx import ASGITransport, AsyncClient, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ChatTurn
from app.main import create_app
from app.services.rag_runtime import RagRuntime
from rag.errors import RetrievalError
from tests.conftest import TITLES, FakeRag, ask, make_settings, new_chat, rag_response


@pytest.mark.parametrize(
    "host",
    # localhost는 ::1과 127.0.0.1로 풀려 asyncpg가 "Multiple exceptions" OSError를 낸다
    ["127.0.0.1", "localhost"],
)
async def test_db_connection_failure_is_503(fake_rag: FakeRag, host: str) -> None:
    settings = make_settings(database_url=f"postgresql+asyncpg://x:x@{host}:1/none")
    runtime = RagRuntime(fake_rag, TITLES, 1, "test", "fake-model")
    app = create_app(settings, rag=runtime)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            response = await http.post("/api/chats", headers={"Origin": "http://chat.example"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "db_unavailable"
    # 브라우저가 오류 코드를 읽을 수 있도록 CORS 헤더가 붙어 있어야 한다
    assert response.headers["access-control-allow-origin"] == "http://chat.example"


async def test_concurrent_feedback_does_not_fail(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    turn_id = (await ask(client, chat_id, headers))["body"]["turn_id"]
    url = f"/api/chats/{chat_id}/turns/{turn_id}/feedback"
    bodies = [{"rating": "up"}, {"rating": "down", "reason": "wrong"}] * 4
    responses = await asyncio.gather(*(client.put(url, json=b, headers=headers) for b in bodies))
    assert [r.status_code for r in responses] == [200] * len(bodies)
    deletes = await asyncio.gather(*(client.delete(url, headers=headers) for _ in range(4)))
    assert [r.status_code for r in deletes] == [204] * 4


async def test_db_connection_is_released_while_waiting_for_rag(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    observed: list[int] = []

    async def watch(question: str, history: list[str]) -> object:
        async with db() as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND state = 'idle in transaction'"
                )
            )
        observed.append(count)
        return rag_response()

    fake_rag.respond = watch
    chat_id, headers = await new_chat(client)
    assert (await ask(client, chat_id, headers))["status"] == 201
    assert observed == [0]


def _quota_error() -> openai.RateLimitError:
    request = Request("POST", "https://api.openai.com/v1/embeddings")
    return openai.RateLimitError(
        "quota", response=Response(429, request=request), body={"code": "insufficient_quota"}
    )


async def test_quota_during_embedding_is_classified_as_quota(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    def fail(question: str, history: list[str]) -> Exception:
        try:
            raise RetrievalError("검색 실패") from _quota_error()
        except RetrievalError as error:
            return error

    fake_rag.respond = fail
    chat_id, headers = await new_chat(client)
    result = await ask(client, chat_id, headers)
    async with db() as session:
        turn = await session.get(ChatTurn, result["body"]["turn_id"])
    assert turn.error_code == "llm_quota"


async def test_method_not_allowed_uses_error_format(client: AsyncClient) -> None:
    response = await client.get("/api/inquiries")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def _from(ip_chain: str) -> dict[str, str]:
    return {"X-Forwarded-For": ip_chain}


@pytest.mark.parametrize(
    "settings_overrides", [{"trusted_proxy_count": 1, "chat_create_per_ip_per_day": 1}]
)
async def test_client_ip_uses_rightmost_trusted_hop(client: AsyncClient) -> None:
    assert (await client.post("/api/chats", headers=_from("6.6.6.6, 1.1.1.1"))).status_code == 201
    # 왼쪽 값을 바꿔도 같은 고객으로 센다 (위조 방지)
    spoofed = await client.post("/api/chats", headers=_from("7.7.7.7, 1.1.1.1"))
    assert spoofed.status_code == 429
    other = await client.post("/api/chats", headers=_from("6.6.6.6, 2.2.2.2"))
    assert other.status_code == 201


@pytest.mark.parametrize(
    "settings_overrides", [{"trusted_proxy_count": 1, "turn_per_ip_per_day": 1}]
)
async def test_daily_turn_limit_follows_chat_creator_ip(client: AsyncClient) -> None:
    created = await client.post("/api/chats", headers=_from("1.1.1.1"))
    chat = created.json()
    auth = {"Authorization": f"Bearer {chat['chat_token']}"}
    url = f"/api/chats/{chat['chat_id']}/turns"

    # 다른 IP에서 질문해도 대화를 만든 IP(1.1.1.1)의 한도로 센다
    first = await client.post(url, json={"question": "질문"}, headers={**auth, **_from("2.2.2.2")})
    assert first.status_code == 201
    second = await client.post(url, json={"question": "질문"}, headers={**auth, **_from("3.3.3.3")})
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "daily_limit_reached"


@pytest.mark.parametrize("settings_overrides", [{"turn_per_ip_per_minute": 2}])
async def test_turn_minute_limit_per_requester_ip(client: AsyncClient) -> None:
    first_id, first_headers = await new_chat(client)
    second_id, second_headers = await new_chat(client)
    await ask(client, first_id, first_headers)
    await ask(client, second_id, second_headers)
    # 대화를 바꿔도 같은 IP의 분 단위 한도에 걸린다
    blocked = await ask(client, first_id, first_headers)
    assert blocked["status"] == 429 and blocked["body"]["error"]["code"] == "rate_limited"


@pytest.mark.parametrize("settings_overrides", [{"chat_create_per_ip_per_minute": 1}])
async def test_chat_creation_minute_limit(client: AsyncClient) -> None:
    await new_chat(client)
    blocked = await client.post("/api/chats")
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"


async def test_inquiry_openapi_marks_token_optional(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    assert spec["paths"]["/api/inquiries"]["post"]["security"] == [{}, {"ChatBearer": []}]


async def test_db_connect_timeout_is_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # asyncpg는 연결 시간 초과를 내장 TimeoutError로 올린다
    async def timeout(*args: object, **kwargs: object) -> int:
        raise TimeoutError

    monkeypatch.setattr(
        "app.repositories.chat_repository.ChatRepository.count_chats_since", timeout
    )
    response = await client.post("/api/chats")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "db_unavailable"


@pytest.mark.parametrize("settings_overrides", [{"inquiry_per_ip_per_hour": 1}])
async def test_concurrent_resend_uses_limit_once(client: AsyncClient) -> None:
    payload = {
        "name": "데모 고객",
        "email": "demo@example.com",
        "content": "동시에 두 번 눌렀어요",
        "origin": "direct_form",
        "request_id": "7d3f0c1e-1111-4a2b-9c3d-000000000001",
    }
    first, second = await asyncio.gather(
        client.post("/api/inquiries", json=payload), client.post("/api/inquiries", json=payload)
    )
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["inquiry_id"] == second.json()["inquiry_id"]


async def test_turn_finish_time_is_taken_after_chat_lock(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    """문의 접수가 대화를 잠그고 있는 동안 끝난 질문은 잠금이 풀린 뒤의 finished_at을 받는다."""
    chat_id, headers = await new_chat(client)
    async with db() as session, session.begin():
        await session.execute(
            text("SELECT id FROM chat WHERE id = :id FOR UPDATE"), {"id": chat_id}
        )
        pending = asyncio.create_task(ask(client, chat_id, headers))
        await asyncio.sleep(0.3)
        assert not pending.done()
        released_at = await session.scalar(text("SELECT clock_timestamp()"))
    result = await pending
    async with db() as session:
        turn = await session.get(ChatTurn, result["body"]["turn_id"])
    assert turn.finished_at > released_at
