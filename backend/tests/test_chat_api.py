"""고객 챗봇 API: 대화 생성, 질문, 피드백, 요청 제한, 오류 형식."""

import asyncio

import openai
import pytest
from httpx import AsyncClient, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ChatTurn, TurnSource
from rag.errors import ParseError, RetrievalError
from tests.conftest import FakeRag, ask, new_chat, rag_response, source


async def test_create_chat_returns_token_once(client: AsyncClient) -> None:
    response = await client.post("/api/chats")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"chat_id", "chat_token", "created_at"}
    assert len(body["chat_token"]) >= 32


async def test_turn_hides_sources_and_stores_them_for_admin(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    # RAG가 같은 FAQ를 두 번 인용해도 한 번만 저장한다. 토큰 0은 측정 안 됨(null)이다
    fake_rag.respond = lambda q, h: rag_response(
        sources=[source("Q02"), source("Q02")],
        retrieved_ids=["Q02", "Q01", "Q02"],
        retrieved_scores=[0.8, 0.4, 0.3],
        prompt_tokens=0,
        completion_tokens=0,
    )
    chat_id, headers = await new_chat(client)
    result = await ask(client, chat_id, headers)

    assert result["status"] == 201
    body = result["body"]
    assert set(body) == {
        "turn_id",
        "chat_id",
        "parent_turn_id",
        "question",
        "mode",
        "answer",
        "show_contact",
        "feedback",
        "created_at",
    }
    assert body["mode"] == "answer" and body["feedback"] is None

    async with db() as session:
        turn = await session.get(ChatTurn, body["turn_id"])
        rows = (await session.scalars(select(TurnSource).order_by(TurnSource.rank))).all()
    assert turn.status == "completed" and turn.reason == "Q02에 있음"
    assert turn.prompt_tokens is None and turn.completion_tokens is None
    assert turn.llm_model == "fake-model" and turn.config_name == "test"
    cited = [(r.source_id, r.rank) for r in rows if r.kind == "cited"]
    retrieved = [(r.source_id, r.rank, r.title) for r in rows if r.kind == "retrieved"]
    assert cited == [("Q02", 1)]
    assert retrieved == [
        ("Q02", 1, "충전은 어떻게 하나요?"),
        ("Q01", 2, "슬리비는 어떤 제품인가요?"),
    ]


async def test_turn_requires_matching_token(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    other_id, other_headers = await new_chat(client)

    no_token = await ask(client, chat_id, {})
    assert no_token["status"] == 401
    assert no_token["body"]["error"]["code"] == "unauthorized"

    # 남의 토큰과 없는 대화는 구별하지 않고 404
    wrong = await ask(client, chat_id, other_headers)
    assert wrong["status"] == 404
    assert wrong["body"]["error"]["code"] == "not_found"


@pytest.mark.parametrize("question", ["   ", "가" * 501])
async def test_question_length_is_validated_after_trim(client: AsyncClient, question: str) -> None:
    chat_id, headers = await new_chat(client)
    result = await ask(client, chat_id, headers, question=question)
    assert result["status"] == 422
    assert result["body"]["error"] == {
        "code": "validation_error",
        "message": "입력값을 확인해 주세요.",
        "fields": ["question"],
    }


async def test_history_follows_parent_chain(client: AsyncClient, fake_rag: FakeRag) -> None:
    chat_id, headers = await new_chat(client)
    first = await ask(client, chat_id, headers, question="슬리비가 뭐예요?")
    await ask(
        client, chat_id, headers, question="케이스는요?", parent_turn_id=first["body"]["turn_id"]
    )
    # 부모 없이 보낸 질문에는 이전 질문을 붙이지 않는다
    await ask(client, chat_id, headers, question="가격은요?")

    assert fake_rag.calls == [
        ("슬리비가 뭐예요?", []),
        ("케이스는요?", ["슬리비가 뭐예요?"]),
        ("가격은요?", []),
    ]


async def test_parent_must_be_completed_turn_of_same_chat(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    chat_id, headers = await new_chat(client)
    other_id, other_headers = await new_chat(client)
    other = await ask(client, other_id, other_headers)

    cross = await ask(client, chat_id, headers, parent_turn_id=other["body"]["turn_id"])
    assert cross["status"] == 422
    assert cross["body"]["error"]["fields"] == ["parent_turn_id"]

    fake_rag.respond = lambda q, h: RuntimeError("down")
    failed = await ask(client, chat_id, headers)
    failed_parent = await ask(client, chat_id, headers, parent_turn_id=failed["body"]["turn_id"])
    assert failed_parent["status"] == 422


def _openai_error(cls: type, code: str) -> Exception:
    request = Request("POST", "https://api.openai.com/v1/chat/completions")
    response = Response(429, request=request)
    return cls("limited", response=response, body={"code": code})


@pytest.mark.parametrize(
    ("error", "error_code"),
    [
        (RetrievalError("qdrant"), "retrieval_error"),
        (ParseError("bad json"), "llm_parse_error"),
        (_openai_error(openai.RateLimitError, "insufficient_quota"), "llm_quota"),
        (_openai_error(openai.RateLimitError, "rate_limit_exceeded"), "llm_rate_limit"),
        (RuntimeError("boom"), "llm_error"),
    ],
)
async def test_rag_failure_saves_failed_turn(
    client: AsyncClient,
    fake_rag: FakeRag,
    db: async_sessionmaker[AsyncSession],
    error: Exception,
    error_code: str,
) -> None:
    fake_rag.respond = lambda q, h: error
    chat_id, headers = await new_chat(client)
    result = await ask(client, chat_id, headers)

    assert result["status"] == 503
    assert result["body"]["error"]["code"] == "ai_unavailable"
    async with db() as session:
        turn = await session.get(ChatTurn, result["body"]["turn_id"])
    # 장애를 unknown 답변으로 바꾸지 않는다
    assert turn.status == "failed" and turn.mode is None and turn.answer is None
    assert turn.error_code == error_code


async def test_rag_timeout_returns_504_with_failed_turn(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    async def slow(question: str, history: list[str]) -> object:
        await asyncio.sleep(5)
        return rag_response()

    fake_rag.respond = slow
    chat_id, headers = await new_chat(client)
    result = await ask(client, chat_id, headers)

    assert result["status"] == 504
    assert result["body"]["error"]["code"] == "ai_timeout"
    async with db() as session:
        turn = await session.get(ChatTurn, result["body"]["turn_id"])
    assert turn.error_code == "llm_timeout"


@pytest.mark.parametrize("settings_overrides", [{"turn_per_chat_per_minute": 2}])
async def test_minute_limit_blocks_without_creating_turn(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    chat_id, headers = await new_chat(client)
    await ask(client, chat_id, headers)
    await ask(client, chat_id, headers)
    blocked = await ask(client, chat_id, headers)

    assert blocked["status"] == 429
    assert blocked["body"]["error"]["code"] == "rate_limited"
    assert int(blocked["headers"]["retry-after"]) > 0
    async with db() as session:
        count = len((await session.scalars(select(ChatTurn))).all())
    assert count == 2


@pytest.mark.parametrize("settings_overrides", [{"turn_per_ip_per_day": 1}])
async def test_daily_limit_counts_only_completed_turns(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    chat_id, headers = await new_chat(client)
    # OpenAI 장애로 실패한 질문은 고객의 하루 한도를 줄이지 않는다
    fake_rag.respond = lambda q, h: RuntimeError("down")
    assert (await ask(client, chat_id, headers))["status"] == 503
    fake_rag.respond = lambda q, h: rag_response()
    assert (await ask(client, chat_id, headers))["status"] == 201

    # 한도는 대화를 만든 IP 기준이라 새 대화를 만들어도 그대로다
    other_id, other_headers = await new_chat(client)
    blocked = await ask(client, other_id, other_headers)
    assert blocked["status"] == 429
    assert blocked["body"]["error"]["code"] == "daily_limit_reached"
    assert int(blocked["headers"]["retry-after"]) > 0


@pytest.mark.parametrize("settings_overrides", [{"turn_global_per_day": 1}])
async def test_global_daily_cap_returns_service_busy(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    await ask(client, chat_id, headers)
    blocked = await ask(client, chat_id, headers)
    assert blocked["status"] == 503
    assert blocked["body"]["error"]["code"] == "service_busy"
    assert "retry-after" in blocked["headers"]


@pytest.mark.parametrize("settings_overrides", [{"chat_create_per_ip_per_day": 1}])
async def test_chat_creation_daily_limit(client: AsyncClient) -> None:
    await new_chat(client)
    blocked = await client.post("/api/chats")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "daily_limit_reached"


async def test_feedback_put_replace_and_delete(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    turn_id = (await ask(client, chat_id, headers))["body"]["turn_id"]
    url = f"/api/chats/{chat_id}/turns/{turn_id}/feedback"

    up = await client.put(url, json={"rating": "up"}, headers=headers)
    assert up.status_code == 200
    assert up.json()["rating"] == "up" and up.json()["reason"] is None

    down = await client.put(url, json={"rating": "down", "reason": "wrong"}, headers=headers)
    assert down.json()["rating"] == "down" and down.json()["reason"] == "wrong"

    invalid = await client.put(url, json={"rating": "up", "reason": "wrong"}, headers=headers)
    assert invalid.status_code == 422

    assert (await client.delete(url, headers=headers)).status_code == 204
    # 이미 취소한 피드백을 다시 취소해도 성공으로 본다
    assert (await client.delete(url, headers=headers)).status_code == 204


async def test_feedback_rules(client: AsyncClient, fake_rag: FakeRag) -> None:
    chat_id, headers = await new_chat(client)
    other_id, other_headers = await new_chat(client)
    turn_id = (await ask(client, chat_id, headers))["body"]["turn_id"]

    # 남의 대화 토큰으로는 평가할 수 없다
    foreign = await client.put(
        f"/api/chats/{other_id}/turns/{turn_id}/feedback",
        json={"rating": "up"},
        headers=other_headers,
    )
    assert foreign.status_code == 404

    fake_rag.respond = lambda q, h: RuntimeError("down")
    failed_id = (await ask(client, chat_id, headers))["body"]["turn_id"]
    on_failed = await client.put(
        f"/api/chats/{chat_id}/turns/{failed_id}/feedback", json={"rating": "up"}, headers=headers
    )
    assert on_failed.status_code == 422


async def test_unknown_route_uses_error_format(client: AsyncClient) -> None:
    response = await client.get("/api/nothing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_cors_exposes_retry_after_to_allowed_origin(client: AsyncClient) -> None:
    allowed = await client.post("/api/chats", headers={"Origin": "http://chat.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://chat.example"
    assert "retry-after" in allowed.headers["access-control-expose-headers"].lower()

    other = await client.post("/api/chats", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
