"""문의 접수 API: 대화 연결 규칙, 중복 접수 방지, 채팅 기록 경계."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Inquiry
from tests.conftest import FakeRag, ask, new_chat, rag_response


def inquiry(**overrides: object) -> dict:
    body: dict = {
        "name": "데모 고객",
        "email": "demo@example.com",
        "content": "한쪽만 따로 살 수 있나요?",
        "origin": "direct_form",
        "request_id": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


async def post(client: AsyncClient, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    response = await client.post("/api/inquiries", json=body, headers=headers or {})
    return response.status_code, response.json()


async def test_direct_form_without_chat(client: AsyncClient) -> None:
    status, body = await post(client, inquiry())
    assert status == 201
    assert body["reference_no"] == "INQ-1001" and body["status"] == "received"


async def test_same_request_id_returns_first_result_or_conflict(client: AsyncClient) -> None:
    payload = inquiry()
    first_status, first = await post(client, payload)
    again_status, again = await post(client, payload)
    assert first_status == again_status == 201
    assert again["inquiry_id"] == first["inquiry_id"]

    status, body = await post(client, {**payload, "content": "내용을 바꿨어요"})
    assert status == 409
    assert body["error"]["code"] == "conflict"


async def test_chat_id_requires_its_token(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    _, other_headers = await new_chat(client)

    status, body = await post(client, inquiry(origin="agent_request", chat_id=chat_id))
    assert status == 401
    status, body = await post(
        client, inquiry(origin="agent_request", chat_id=chat_id), other_headers
    )
    assert status == 404


async def test_started_chat_needs_trigger_and_records_boundary(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    chat_id, headers = await new_chat(client)
    completed = (await ask(client, chat_id, headers))["body"]["turn_id"]
    # 마지막 저장 turn은 실패 turn이어도 경계가 된다
    fake_rag.respond = lambda q, h: RuntimeError("down")
    failed = (await ask(client, chat_id, headers))["body"]["turn_id"]

    status, body = await post(client, inquiry(chat_id=chat_id), headers)
    assert status == 422
    assert body["error"]["fields"] == ["trigger_turn_id"]

    status, body = await post(client, inquiry(chat_id=chat_id, trigger_turn_id=completed), headers)
    assert status == 201
    async with db() as session:
        saved = await session.get(Inquiry, body["inquiry_id"])
    assert str(saved.trigger_turn_id) == completed
    assert str(saved.context_last_turn_id) == failed


async def test_only_failed_turns_attach_chat_without_trigger(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    fake_rag.respond = lambda q, h: RuntimeError("down")
    chat_id, headers = await new_chat(client)
    failed = (await ask(client, chat_id, headers))["body"]["turn_id"]

    status, body = await post(client, inquiry(chat_id=chat_id), headers)
    assert status == 201
    async with db() as session:
        saved = await session.get(Inquiry, body["inquiry_id"])
    assert saved.trigger_turn_id is None and str(saved.context_last_turn_id) == failed


async def test_card_needs_trigger_with_show_contact(client: AsyncClient, fake_rag: FakeRag) -> None:
    chat_id, headers = await new_chat(client)
    plain = (await ask(client, chat_id, headers))["body"]["turn_id"]
    fake_rag.respond = lambda q, h: rag_response(mode="partial", show_contact=True)
    carded = (await ask(client, chat_id, headers))["body"]["turn_id"]

    status, _ = await post(
        client,
        inquiry(origin="uncertain_answer_card", chat_id=chat_id, trigger_turn_id=plain),
        headers,
    )
    assert status == 422
    status, _ = await post(
        client,
        inquiry(origin="uncertain_answer_card", chat_id=chat_id, trigger_turn_id=carded),
        headers,
    )
    assert status == 201


async def test_agent_request_rules(client: AsyncClient) -> None:
    status, body = await post(client, inquiry(origin="agent_request"))
    assert status == 422 and body["error"]["fields"] == ["chat_id"]

    # 질문 전에 상담사 연결을 누르면 chat_id만 보낸다
    chat_id, headers = await new_chat(client)
    status, _ = await post(client, inquiry(origin="agent_request", chat_id=chat_id), headers)
    assert status == 201


async def test_trigger_must_belong_to_chat(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    other_id, other_headers = await new_chat(client)
    await ask(client, chat_id, headers)
    foreign = (await ask(client, other_id, other_headers))["body"]["turn_id"]

    status, body = await post(client, inquiry(chat_id=chat_id, trigger_turn_id=foreign), headers)
    assert status == 422 and body["error"]["fields"] == ["trigger_turn_id"]

    status, body = await post(client, inquiry(trigger_turn_id=foreign))
    assert status == 422 and body["error"]["fields"] == ["chat_id"]


@pytest.mark.parametrize(
    "overrides",
    [{"name": "  "}, {"email": "not-an-email"}, {"content": "가" * 2001}, {"origin": "phone"}],
)
async def test_inquiry_input_validation(client: AsyncClient, overrides: dict) -> None:
    status, body = await post(client, inquiry(**overrides))
    assert status == 422
    assert body["error"]["fields"] == [next(iter(overrides))]


@pytest.mark.parametrize("settings_overrides", [{"inquiry_per_ip_per_hour": 1}])
async def test_inquiry_hourly_limit(client: AsyncClient) -> None:
    assert (await post(client, inquiry()))[0] == 201
    status, body = await post(client, inquiry())
    assert status == 429 and body["error"]["code"] == "rate_limited"
