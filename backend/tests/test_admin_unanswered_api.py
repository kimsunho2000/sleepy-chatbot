"""미답변 통합 테스트. 기존 fixture가 테스트 DB를 초기화하므로 확인 후 실행한다."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import issue_admin_token
from app.db.models import Chat, ChatTurn, Feedback, Inquiry, TurnSource
from tests.conftest import ADMIN_PASSWORD

BASE = "/api/admin/unanswered-groups"
NOW = datetime(2026, 11, 14, 0, tzinfo=UTC)
PERIOD = {"from": "2026-11-01T00:00:00Z", "to": "2026-12-01T00:00:00Z"}


async def admin_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/admin/tokens", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def seed(
    db: async_sessionmaker[AsyncSession],
    *,
    mode: str = "unknown",
    rating: str | None = None,
    source: str | None = "Q01",
    question: str = "질문",
    at: datetime = NOW,
    failed: bool = False,
    inquiries: int = 0,
) -> uuid.UUID:
    chat_id, turn_id = uuid.uuid4(), uuid.uuid4()
    async with db() as session:
        session.add(
            Chat(
                id=chat_id,
                token_hash=uuid.uuid4().hex * 2,
                client_ip_hash="i" * 64,
                created_at=at,
            )
        )
        await session.flush()
        session.add(
            ChatTurn(
                id=turn_id,
                chat_id=chat_id,
                question=question,
                status="failed" if failed else "completed",
                mode=None if failed else mode,
                answer=None if failed else "답변",
                error_code="llm_error" if failed else None,
                show_contact=False,
                llm_model="fake",
                config_name="test",
                created_at=at,
                finished_at=at,
            )
        )
        await session.flush()
        if source is not None:
            session.add(
                TurnSource(
                    turn_id=turn_id,
                    kind="retrieved",
                    rank=1,
                    source_id=source,
                    title=f"제목 {source}",
                    score=0.5,
                )
            )
            # 인용 출처는 그룹화와 횟수에 영향을 주지 않아야 한다.
            session.add(
                TurnSource(
                    turn_id=turn_id,
                    kind="cited",
                    rank=1,
                    source_id="OTHER",
                    title="다른 출처",
                    score=0.9,
                )
            )
        if rating is not None:
            session.add(
                Feedback(
                    turn_id=turn_id,
                    rating=rating,
                    reason=None,
                    created_at=at,
                    updated_at=at,
                )
            )
        for _ in range(inquiries):
            session.add(
                Inquiry(
                    request_id=uuid.uuid4(),
                    chat_id=chat_id,
                    trigger_turn_id=turn_id,
                    context_last_turn_id=turn_id,
                    name="비공개 이름",
                    email="private@example.com",
                    content="비공개 문의",
                    origin="direct_form",
                    status="received",
                    internal_note="비공개 메모",
                    created_at=at,
                    updated_at=at,
                )
            )
        await session.commit()
    return turn_id


async def test_groups_classification_and_no_join_multiplication(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await seed(db, mode="partial", rating="down", inquiries=2)
    await seed(db, mode="unknown", question="최신 질문", at=NOW + timedelta(seconds=1))
    await seed(db, mode="answer", rating="down")
    await seed(db, mode="answer")
    await seed(db, mode="answer", rating="up")
    await seed(db, failed=True)
    response = await client.get(BASE, params=PERIOD, headers=await admin_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    group = body["items"][0]
    assert group["occurrence_count"] == 3
    assert (group["unknown_count"], group["partial_count"], group["downvote_count"]) == (1, 1, 2)
    assert group["representative_question"] == "최신 질문"
    assert len(group["inquiries"]) == 2
    assert set(group["inquiries"][0]) == {"id", "reference_no"}
    assert "private@example.com" not in response.text
    assert "비공개 메모" not in response.text


async def test_detail_variants_and_turn_pagination(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await seed(db, question="같은 질문", inquiries=2)
    await seed(db, question="같은 질문", at=NOW + timedelta(seconds=1))
    newest = await seed(db, question="다른 질문", at=NOW + timedelta(seconds=2))
    headers = await admin_headers(client)
    response = await client.get(BASE + "/Q01", params={**PERIOD, "size": 1}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["variants"][0] == {"question": "같은 질문", "count": 2}
    assert body["turns"]["total_count"] == 3
    assert body["turns"]["items"][0]["turn_id"] == str(newest)
    empty = await client.get(BASE + "/Q01", params={**PERIOD, "page": 10}, headers=headers)
    assert empty.json()["turns"]["items"] == []


async def test_empty_and_missing_group(client: AsyncClient) -> None:
    headers = await admin_headers(client)
    response = await client.get(BASE, params=PERIOD, headers=headers)
    assert response.json() == {"items": [], "page": 1, "size": 20, "total_count": 0}
    missing = await client.get(BASE + "/missing", params=PERIOD, headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_no_search_result_and_reserved_key(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await seed(db, source=None)
    headers = await admin_headers(client)
    response = await client.get(BASE + "/none", params=PERIOD, headers=headers)
    assert response.status_code == 200
    assert response.json()["group"]["source_title"] is None
    await seed(db, source="none")
    response = await client.get(BASE, params=PERIOD, headers=headers)
    assert response.status_code == 409


async def test_feedback_removal_changes_membership(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    turn_id = await seed(db, mode="answer", rating="down")
    headers = await admin_headers(client)
    assert (await client.get(BASE, params=PERIOD, headers=headers)).json()["total_count"] == 1
    async with db() as session:
        feedback = await session.get(Feedback, turn_id)
        await session.delete(feedback)
        await session.commit()
    assert (await client.get(BASE, params=PERIOD, headers=headers)).json()["total_count"] == 0


async def test_period_boundaries_and_group_order(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    await seed(db, source="Q02", at=NOW)
    await seed(db, source="Q01", at=NOW)
    await seed(db, source="Q03", at=NOW + timedelta(days=1))
    headers = await admin_headers(client)
    params = {"from": NOW.isoformat(), "to": (NOW + timedelta(days=1)).isoformat(), "size": 1}
    response = await client.get(BASE, params=params, headers=headers)
    assert response.json()["total_count"] == 2
    assert response.json()["items"][0]["group_key"] == "Q01"
    response = await client.get(BASE, params={**params, "page": 2}, headers=headers)
    assert response.json()["items"][0]["group_key"] == "Q02"


@pytest.mark.parametrize("path", [BASE, BASE + "/Q01"])
@pytest.mark.parametrize("kind", ["missing", "garbage", "expired", "tampered", "customer"])
async def test_admin_authentication(client: AsyncClient, path: str, kind: str) -> None:
    headers = {}
    if kind == "customer":
        chat = await client.post("/api/chats")
        headers = {"Authorization": f"Bearer {chat.json()['chat_token']}"}
    elif kind in ("expired", "tampered"):
        token, _ = issue_admin_token(
            "admin",
            "관리자",
            "t" * 32 if kind == "expired" else "x" * 32,
            timedelta(hours=-1 if kind == "expired" else 1),
        )
        headers = {"Authorization": f"Bearer {token}"}
    elif kind == "garbage":
        headers = {"Authorization": "Bearer invalid"}
    response = await client.get(path, params=PERIOD, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"size": 101},
        {"size": 0},
        {"from": "invalid"},
        {"from": "2026-11-14T00:00:00"},
        {"from": "2026-11-15T00:00:00Z", "to": "2026-11-14T00:00:00Z"},
    ],
)
async def test_query_validation(client: AsyncClient, params: dict) -> None:
    response = await client.get(BASE, params=params, headers=await admin_headers(client))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
