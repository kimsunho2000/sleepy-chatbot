"""관리자 질문 로그(목록·상세)와 대시보드 API."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import KST
from app.db.models import ChatTurn, Inquiry
from rag.errors import RetrievalError
from tests.conftest import ADMIN_PASSWORD, FakeRag, ask, new_chat, rag_response, source

# 한 테스트에서 질문을 많이 만들므로 요청 제한을 넉넉히 둔다
HIGH_LIMITS = {
    "chat_create_per_ip_per_minute": 1000,
    "turn_per_chat_per_minute": 1000,
    "turn_per_ip_per_minute": 1000,
    "inquiry_per_ip_per_hour": 1000,
}
PRICES = {"llm_input_price_per_1m_tokens": 0.4, "llm_output_price_per_1m_tokens": 1.6}


@pytest.fixture
def settings_overrides() -> dict:
    return HIGH_LIMITS


async def admin_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/admin/tokens", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def make_turn(
    client: AsyncClient,
    fake_rag: FakeRag,
    result: object | None = None,
    question: str = "충전은 어떻게 하나요?",
) -> dict:
    fake_rag.respond = lambda q, h: result if result is not None else rag_response()
    chat_id, headers = await new_chat(client)
    response = await ask(client, chat_id, headers, question)
    # response의 headers는 응답 헤더라 대화 토큰 헤더는 auth로 따로 둔다
    return {**response, "chat_id": chat_id, "auth": headers}


async def set_created_at(
    db: async_sessionmaker[AsyncSession], turn_id: str, created_at: datetime
) -> None:
    async with db() as session:
        await session.execute(
            update(ChatTurn)
            .where(ChatTurn.id == uuid.UUID(turn_id))
            .values(created_at=created_at, finished_at=created_at)
        )
        await session.commit()


async def put_feedback(client: AsyncClient, turn: dict, rating: str) -> None:
    response = await client.put(
        f"/api/chats/{turn['chat_id']}/turns/{turn['body']['turn_id']}/feedback",
        json={"rating": rating},
        headers=turn["auth"],
    )
    assert response.status_code == 200, response.text


# ---- 공통 ----


@pytest.mark.parametrize(
    "path", ["/api/admin/turns", f"/api/admin/turns/{uuid.uuid4()}", "/api/admin/dashboard"]
)
async def test_admin_log_apis_require_admin_token(client: AsyncClient, path: str) -> None:
    for headers in ({}, {"Authorization": "Bearer not-a-token"}):
        response = await client.get(path, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


async def test_chat_token_is_not_admin_token(client: AsyncClient, fake_rag: FakeRag) -> None:
    turn = await make_turn(client, fake_rag)
    response = await client.get("/api/admin/turns", headers=turn["auth"])
    assert response.status_code == 401


async def test_openapi_lists_admin_log_apis(client: AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "get" in paths["/api/admin/turns"]
    assert "get" in paths["/api/admin/turns/{turn_id}"]
    assert "get" in paths["/api/admin/dashboard"]


# ---- 질문 로그 목록 ----


async def test_list_turns_newest_first_with_rating(client: AsyncClient, fake_rag: FakeRag) -> None:
    first = await make_turn(client, fake_rag, question="첫 질문")
    second = await make_turn(client, fake_rag, question="두 번째 질문")
    await put_feedback(client, first, "up")
    admin = await admin_headers(client)

    response = await client.get("/api/admin/turns", headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1 and body["size"] == 20 and body["total_count"] == 2
    assert [i["turn_id"] for i in body["items"]] == [
        second["body"]["turn_id"],
        first["body"]["turn_id"],
    ]
    item = body["items"][1]
    assert set(item) == {
        "turn_id",
        "chat_id",
        "question",
        "status",
        "mode",
        "latency_ms",
        "rating",
        "created_at",
    }
    assert item["rating"] == "up" and item["status"] == "completed" and item["mode"] == "answer"
    assert body["items"][0]["rating"] is None


async def test_list_turns_filters(client: AsyncClient, fake_rag: FakeRag) -> None:
    answered = await make_turn(client, fake_rag, question="답변")
    unknown = await make_turn(client, fake_rag, rag_response(mode="unknown"), "모름")
    failed = await make_turn(client, fake_rag, RetrievalError("qdrant"), "실패")
    assert failed["status"] == 503
    await put_feedback(client, answered, "down")
    admin = await admin_headers(client)

    async def ids(**params: str) -> list[str]:
        response = await client.get("/api/admin/turns", params=params, headers=admin)
        assert response.status_code == 200, response.text
        return [item["turn_id"] for item in response.json()["items"]]

    failed_id = failed["body"]["turn_id"]
    assert await ids(mode="unknown") == [unknown["body"]["turn_id"]]
    assert await ids(status="failed") == [failed_id]
    assert await ids(rating="down") == [answered["body"]["turn_id"]]
    assert set(await ids(rating="none")) == {unknown["body"]["turn_id"], failed_id}
    assert await ids(chat_id=unknown["chat_id"]) == [unknown["body"]["turn_id"]]

    failed_item = await client.get("/api/admin/turns", params={"status": "failed"}, headers=admin)
    item = failed_item.json()["items"][0]
    assert item["mode"] is None and item["latency_ms"] is None


async def test_list_turns_of_one_chat_oldest_first(client: AsyncClient) -> None:
    chat_id, headers = await new_chat(client)
    first = await ask(client, chat_id, headers, "첫 질문")
    second = await ask(client, chat_id, headers, "다음 질문", first["body"]["turn_id"])
    admin = await admin_headers(client)

    response = await client.get("/api/admin/turns", params={"chat_id": chat_id}, headers=admin)
    assert [i["turn_id"] for i in response.json()["items"]] == [
        first["body"]["turn_id"],
        second["body"]["turn_id"],
    ]


async def test_list_turns_period_includes_from_excludes_to(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    start = datetime(2026, 11, 1, tzinfo=UTC)
    at_start = await make_turn(client, fake_rag, question="시작 시각")
    at_end = await make_turn(client, fake_rag, question="끝 시각")
    await set_created_at(db, at_start["body"]["turn_id"], start)
    await set_created_at(db, at_end["body"]["turn_id"], start + timedelta(days=1))
    admin = await admin_headers(client)

    params = {"from": start.isoformat(), "to": (start + timedelta(days=1)).isoformat()}
    response = await client.get("/api/admin/turns", params=params, headers=admin)
    assert [i["turn_id"] for i in response.json()["items"]] == [at_start["body"]["turn_id"]]


async def test_list_turns_pagination(client: AsyncClient, fake_rag: FakeRag) -> None:
    created = [(await make_turn(client, fake_rag, question=f"질문 {n}"))["body"] for n in range(3)]
    admin = await admin_headers(client)

    response = await client.get("/api/admin/turns", params={"page": 2, "size": 2}, headers=admin)
    body = response.json()
    assert body["total_count"] == 3 and body["page"] == 2 and body["size"] == 2
    assert [i["turn_id"] for i in body["items"]] == [created[0]["turn_id"]]


@pytest.mark.parametrize(
    "params",
    [
        {"size": "101"},
        {"size": "0"},
        {"page": "0"},
        {"mode": "maybe"},
        {"status": "running"},
        {"rating": "meh"},
        {"chat_id": "not-a-uuid"},
        {"from": "2026-11-02T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        {"from": "2026-11-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        # 시간대가 없으면 UTC인지 한국 시각인지 알 수 없다
        {"from": "2026-11-01T00:00:00"},
    ],
)
async def test_list_turns_rejects_invalid_params(client: AsyncClient, params: dict) -> None:
    admin = await admin_headers(client)
    response = await client.get("/api/admin/turns", params=params, headers=admin)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---- 질문 로그 상세 ----


async def test_turn_detail_has_admin_only_fields(client: AsyncClient, fake_rag: FakeRag) -> None:
    # RAG가 같은 FAQ를 두 번 인용해도 상세에는 한 번만 나온다
    result = rag_response(
        sources=[source("Q02", 0.8), source("Q02", 0.8), source("Q01", 0.5)],
        retrieved_ids=["Q02", "Q01", "Q02"],
        retrieved_scores=[0.8, 0.5, 0.3],
    )
    turn = await make_turn(client, fake_rag, result)
    assert "cited_sources" not in turn["body"] and "reason" not in turn["body"]
    await put_feedback(client, turn, "up")
    admin = await admin_headers(client)

    response = await client.get(f"/api/admin/turns/{turn['body']['turn_id']}", headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed" and body["mode"] == "answer"
    assert body["reason"] == "Q02에 있음" and body["error_code"] is None
    assert [(s["rank"], s["source_id"]) for s in body["cited_sources"]] == [(1, "Q02"), (2, "Q01")]
    assert [(s["rank"], s["source_id"], s["title"]) for s in body["retrieved_sources"]] == [
        (1, "Q02", "충전은 어떻게 하나요?"),
        (2, "Q01", "슬리비는 어떤 제품인가요?"),
    ]
    assert body["prompt_tokens"] == 100 and body["completion_tokens"] == 20
    assert body["llm_model"] == "fake-model" and body["config_name"] == "test"
    assert body["feedback"]["rating"] == "up" and body["feedback"]["reason"] is None
    assert body["inquiries"] == []
    # 단가를 정하지 않았으면 비용을 추측하지 않는다
    assert body["estimated_cost_usd"] is None


async def test_failed_turn_detail_keeps_error_code(client: AsyncClient, fake_rag: FakeRag) -> None:
    turn = await make_turn(client, fake_rag, RetrievalError("qdrant"))
    admin = await admin_headers(client)

    body = (await client.get(f"/api/admin/turns/{turn['body']['turn_id']}", headers=admin)).json()
    assert body["status"] == "failed" and body["error_code"] == "retrieval_error"
    assert body["mode"] is None and body["answer"] is None
    assert body["cited_sources"] == [] and body["retrieved_sources"] == []
    assert body["estimated_cost_usd"] is None and body["feedback"] is None


@pytest.mark.parametrize("settings_overrides", [{**HIGH_LIMITS, **PRICES}])
async def test_turn_detail_cost_uses_configured_prices(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    priced = await make_turn(client, fake_rag)
    # 토큰을 측정하지 못한 turn(0 → null)은 단가가 있어도 비용이 없다
    unmeasured = await make_turn(client, fake_rag, rag_response(prompt_tokens=0))
    admin = await admin_headers(client)

    body = (await client.get(f"/api/admin/turns/{priced['body']['turn_id']}", headers=admin)).json()
    assert body["estimated_cost_usd"] == pytest.approx((100 * 0.4 + 20 * 1.6) / 1_000_000)
    path = f"/api/admin/turns/{unmeasured['body']['turn_id']}"
    assert (await client.get(path, headers=admin)).json()["estimated_cost_usd"] is None


async def test_turn_detail_lists_linked_inquiries(client: AsyncClient, fake_rag: FakeRag) -> None:
    turn = await make_turn(client, fake_rag)
    response = await client.post(
        "/api/inquiries",
        json={
            "name": "데모 고객",
            "email": "demo@example.com",
            "content": "상담을 원해요",
            "origin": "agent_request",
            "chat_id": turn["chat_id"],
            "trigger_turn_id": turn["body"]["turn_id"],
            "request_id": str(uuid.uuid4()),
        },
        headers=turn["auth"],
    )
    assert response.status_code == 201, response.text
    admin = await admin_headers(client)

    body = (await client.get(f"/api/admin/turns/{turn['body']['turn_id']}", headers=admin)).json()
    assert body["inquiries"] == [
        {"id": response.json()["inquiry_id"], "reference_no": response.json()["reference_no"]}
    ]


async def test_turn_detail_not_found(client: AsyncClient) -> None:
    admin = await admin_headers(client)
    response = await client.get(f"/api/admin/turns/{uuid.uuid4()}", headers=admin)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ---- 대시보드 ----


async def get_dashboard(client: AsyncClient, admin: dict, **params: str) -> dict:
    response = await client.get("/api/admin/dashboard", params=params, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


async def test_empty_dashboard_uses_null_for_missing_values(client: AsyncClient) -> None:
    body = await get_dashboard(client, await admin_headers(client))
    assert body["question_count"] == 0 and body["failed_count"] == 0
    assert set(body["mode_counts"].values()) == {0}
    assert set(body["failed_by_reason"].values()) == {0}
    for key in (
        "average_latency_ms",
        "uncertain_ratio",
        "positive_feedback_ratio",
        "estimated_cost_usd",
        "average_cost_usd",
    ):
        assert body[key] is None, key
    assert body["feedback_count"] == 0 and body["top_sources"] == []
    assert body["unresolved_inquiry_count"] == 0 and body["unread_inquiry_count"] == 0


async def test_dashboard_default_period_is_last_7_kst_days(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    await make_turn(client, fake_rag, question="오늘")
    old = await make_turn(client, fake_rag, question="8일 전")
    await set_created_at(db, old["body"]["turn_id"], datetime.now(UTC) - timedelta(days=8))

    body = await get_dashboard(client, await admin_headers(client))
    today = datetime.now(KST).date()
    days = [d["date"] for d in body["daily_questions"]]
    assert days == [(today - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    assert body["question_count"] == 1 and body["daily_questions"][-1]["count"] == 1
    assert datetime.fromisoformat(body["to"]) - datetime.fromisoformat(body["from"]) == timedelta(
        days=7
    )


async def test_dashboard_counts_and_ratios(client: AsyncClient, fake_rag: FakeRag) -> None:
    answered = await make_turn(client, fake_rag, rag_response(latency_ms=100.0))
    partial = await make_turn(client, fake_rag, rag_response(mode="partial", latency_ms=300.0))
    await make_turn(client, fake_rag, rag_response(mode="unknown", sources=[], latency_ms=200.0))
    # 인사·범위 밖 질문은 불확실 답변 비율의 분모에서 뺀다
    await make_turn(client, fake_rag, rag_response(mode="greeting", sources=[], latency_ms=200.0))
    await make_turn(client, fake_rag, rag_response(mode="offtopic", sources=[], latency_ms=200.0))
    await make_turn(client, fake_rag, RetrievalError("qdrant"))
    await put_feedback(client, answered, "up")
    await put_feedback(client, partial, "down")

    body = await get_dashboard(client, await admin_headers(client))
    assert body["question_count"] == 6
    assert body["mode_counts"] == {
        "answer": 1,
        "partial": 1,
        "unknown": 1,
        "offtopic": 1,
        "greeting": 1,
    }
    assert body["failed_count"] == 1 and body["failed_by_reason"]["retrieval_error"] == 1
    assert body["uncertain_ratio"] == pytest.approx(2 / 3)
    # 실패 turn은 응답 시간이 없으므로 평균에서 빠진다
    assert body["average_latency_ms"] == pytest.approx(200.0)
    assert body["feedback_count"] == 2 and body["positive_feedback_ratio"] == pytest.approx(0.5)
    assert sum(d["count"] for d in body["daily_questions"]) == body["question_count"]
    assert body["estimated_cost_usd"] is None and body["average_cost_usd"] is None


async def test_dashboard_reflects_feedback_change_and_cancel(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    turn = await make_turn(client, fake_rag)
    admin = await admin_headers(client)
    await put_feedback(client, turn, "up")
    assert (await get_dashboard(client, admin))["positive_feedback_ratio"] == 1.0

    await put_feedback(client, turn, "down")
    assert (await get_dashboard(client, admin))["positive_feedback_ratio"] == 0.0

    path = f"/api/chats/{turn['chat_id']}/turns/{turn['body']['turn_id']}/feedback"
    assert (await client.delete(path, headers=turn["auth"])).status_code == 204
    body = await get_dashboard(client, admin)
    assert body["feedback_count"] == 0 and body["positive_feedback_ratio"] is None


async def test_dashboard_daily_questions_split_at_kst_midnight(
    client: AsyncClient, fake_rag: FakeRag, db: async_sessionmaker[AsyncSession]
) -> None:
    # 한국 11월 2일 자정 = UTC 11월 1일 15:00
    midnight = datetime(2026, 11, 1, 15, tzinfo=UTC)
    before = await make_turn(client, fake_rag, question="자정 직전")
    after = await make_turn(client, fake_rag, question="자정")
    await set_created_at(db, before["body"]["turn_id"], midnight - timedelta(seconds=1))
    await set_created_at(db, after["body"]["turn_id"], midnight)

    params = {
        "from": datetime(2026, 10, 31, 15, tzinfo=UTC).isoformat(),
        "to": datetime(2026, 11, 2, 15, tzinfo=UTC).isoformat(),
    }
    body = await get_dashboard(client, await admin_headers(client), **params)
    assert body["daily_questions"] == [
        {"date": "2026-11-01", "count": 1},
        {"date": "2026-11-02", "count": 1},
    ]


@pytest.mark.parametrize("settings_overrides", [{**HIGH_LIMITS, **PRICES}])
async def test_dashboard_cost_with_prices(client: AsyncClient, fake_rag: FakeRag) -> None:
    await make_turn(client, fake_rag)
    await make_turn(client, fake_rag, rag_response(prompt_tokens=300, completion_tokens=60))
    # 토큰이 없는 turn은 비용 합과 평균 모두에서 빠진다
    await make_turn(client, fake_rag, rag_response(prompt_tokens=0, completion_tokens=0))

    body = await get_dashboard(client, await admin_headers(client))
    total = (400 * 0.4 + 80 * 1.6) / 1_000_000
    assert body["estimated_cost_usd"] == pytest.approx(total)
    assert body["average_cost_usd"] == pytest.approx(total / 2)


async def test_dashboard_top_sources_counts_each_answer_once(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    # Q02를 한 답변에서 두 번 인용해도 1로 센다
    await make_turn(client, fake_rag, rag_response(sources=[source("Q02"), source("Q02")]))
    await make_turn(client, fake_rag, rag_response(sources=[source("Q02"), source("Q01")]))
    for faq_id in ("Q01", "Q03", "Q04", "Q05", "Q06"):
        await make_turn(client, fake_rag, rag_response(sources=[source(faq_id)]))
    # 검색 후보로만 나온 FAQ는 세지 않는다
    await make_turn(
        client, fake_rag, rag_response(sources=[], retrieved_ids=["Q09"], retrieved_scores=[0.9])
    )

    body = await get_dashboard(client, await admin_headers(client))
    assert body["top_sources"] == [
        {"source_id": "Q01", "title": "슬리비는 어떤 제품인가요?", "count": 2},
        {"source_id": "Q02", "title": "충전은 어떻게 하나요?", "count": 2},
        {"source_id": "Q03", "title": "Q03", "count": 1},
        {"source_id": "Q04", "title": "Q04", "count": 1},
        {"source_id": "Q05", "title": "Q05", "count": 1},
    ]


async def test_dashboard_inquiry_counts_ignore_period(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    ids = []
    for _ in range(3):
        response = await client.post(
            "/api/inquiries",
            json={
                "name": "데모 고객",
                "email": "demo@example.com",
                "content": "문의합니다",
                "origin": "direct_form",
                "request_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 201, response.text
        ids.append(uuid.UUID(response.json()["inquiry_id"]))
    now = datetime.now(UTC)
    async with db() as session:
        # 읽음 처리는 상태를 바꾸지 않는다. 완료했지만 열어 보지 않은 문의는 미확인으로 남는다
        await session.execute(
            update(Inquiry).where(Inquiry.id == ids[0]).values(first_viewed_at=now)
        )
        await session.execute(
            update(Inquiry).where(Inquiry.id == ids[1]).values(status="completed", completed_at=now)
        )
        await session.commit()

    # 문의가 없는 먼 과거 기간이어도 문의 수는 전체 기준이다
    params = {"from": "2020-01-01T00:00:00Z", "to": "2020-01-08T00:00:00Z"}
    body = await get_dashboard(client, await admin_headers(client), **params)
    assert body["question_count"] == 0
    assert body["unresolved_inquiry_count"] == 2
    assert body["unread_inquiry_count"] == 2


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-02T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        {"from": "2025-01-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        {"to": "2026-11-01T00:00:00"},
    ],
    ids=["reversed", "too-long", "naive"],
)
async def test_dashboard_rejects_invalid_period(client: AsyncClient, params: dict) -> None:
    response = await client.get(
        "/api/admin/dashboard", params=params, headers=await admin_headers(client)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
