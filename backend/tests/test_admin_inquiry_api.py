"""관리자 문의 관리 API: 목록, 상태별 건수, 상세(채팅 기록), 읽음·상태·메모 수정."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Inquiry
from tests.conftest import ADMIN_PASSWORD, FakeRag, ask, new_chat, rag_response


@pytest.fixture
def settings_overrides() -> dict:
    # 여러 문의를 만드는 테스트가 고객 문의 시간당 한도에 걸리지 않게 한다
    return {"inquiry_per_ip_per_hour": 1000, "chat_create_per_ip_per_minute": 100}


async def admin(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/admin/tokens", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def make_inquiry(
    client: AsyncClient, headers: dict | None = None, **overrides: object
) -> dict:
    body: dict = {
        "name": "데모 고객",
        "email": "demo@example.com",
        "content": "한쪽만 따로 살 수 있나요?",
        "origin": "direct_form",
        "request_id": str(uuid.uuid4()),
    }
    body.update(overrides)
    response = await client.post("/api/inquiries", json=body, headers=headers or {})
    assert response.status_code == 201, response.text
    return response.json()


async def patch(client: AsyncClient, token: dict, inquiry_id: str, body: dict) -> tuple[int, dict]:
    response = await client.patch(f"/api/admin/inquiries/{inquiry_id}", json=body, headers=token)
    return response.status_code, response.json()


async def detail(client: AsyncClient, token: dict, inquiry_id: str) -> dict:
    response = await client.get(f"/api/admin/inquiries/{inquiry_id}", headers=token)
    assert response.status_code == 200, response.text
    return response.json()


async def make_in_order(
    client: AsyncClient, db: async_sessionmaker[AsyncSession], names: list[str]
) -> list[dict]:
    """접수 시각이 서로 다르게 고정된 문의들. 서버 시계가 거칠어도(Windows는 약 15ms) 순서가 흔들리지 않는다."""
    created = []
    for index, name in enumerate(names):
        inquiry = await make_inquiry(client, name=name)
        await set_created_at(
            db, inquiry["inquiry_id"], datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=index)
        )
        created.append(inquiry)
    return created


async def listing(client: AsyncClient, token: dict, **params: object) -> dict:
    response = await client.get("/api/admin/inquiries", params=params, headers=token)
    assert response.status_code == 200, response.text
    return response.json()


async def counts(client: AsyncClient, token: dict, **params: object) -> dict:
    response = await client.get("/api/admin/inquiry-counts", params=params, headers=token)
    assert response.status_code == 200, response.text
    return response.json()


async def set_created_at(
    db: async_sessionmaker[AsyncSession], inquiry_id: str, created_at: datetime
) -> None:
    async with db() as session:
        await session.execute(
            update(Inquiry).where(Inquiry.id == uuid.UUID(inquiry_id)).values(created_at=created_at)
        )
        await session.commit()


# ---------- 접근 ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/inquiries"),
        ("GET", "/api/admin/inquiry-counts"),
        ("GET", f"/api/admin/inquiries/{uuid.uuid4()}"),
        ("PATCH", f"/api/admin/inquiries/{uuid.uuid4()}"),
    ],
)
async def test_every_endpoint_requires_admin_token(
    client: AsyncClient, method: str, path: str
) -> None:
    body = {"json": {"viewed": True}} if method == "PATCH" else {}
    missing = await client.request(method, path, **body)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"

    # 고객 대화 토큰으로는 관리자 API를 쓸 수 없다
    _, chat_headers = await new_chat(client)
    customer = await client.request(method, path, headers=chat_headers, **body)
    assert customer.status_code == 401


# ---------- 목록 ----------


async def test_list_defaults_to_unresolved_newest_first(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    token = await admin(client)
    first, second, third = await make_in_order(client, db, ["첫째", "둘째", "셋째"])
    await patch(client, token, first["inquiry_id"], {"status": "completed"})
    await patch(client, token, second["inquiry_id"], {"status": "in_progress"})

    body = await listing(client, token)
    # 기본은 처리 전(received + in_progress)이고 최신순이다
    assert [item["name"] for item in body["items"]] == ["셋째", "둘째"]
    assert body["total_count"] == 2 and body["page"] == 1 and body["size"] == 20

    assert (await listing(client, token, status="all"))["total_count"] == 3
    assert [i["id"] for i in (await listing(client, token, status="completed"))["items"]] == [
        first["inquiry_id"]
    ]
    assert [i["id"] for i in (await listing(client, token, status="received"))["items"]] == [
        third["inquiry_id"]
    ]


async def test_list_item_has_only_summary_fields(client: AsyncClient) -> None:
    token = await admin(client)
    long_content = "배송이 너무 늦어요.\n\n   " + "주문 번호를 확인해 주세요. " * 20
    await make_inquiry(client, content=long_content)

    item = (await listing(client, token))["items"][0]
    assert set(item) == {
        "id",
        "reference_no",
        "name",
        "content_preview",
        "origin",
        "status",
        "is_unread",
        "has_conversation",
        "created_at",
    }
    assert item["is_unread"] is True and item["has_conversation"] is False
    # 줄바꿈과 연속 공백은 한 칸으로 줄이고, 길면 …로 자른다
    assert "\n" not in item["content_preview"] and "  " not in item["content_preview"]
    assert len(item["content_preview"]) <= 80 and item["content_preview"].endswith("…")


async def test_short_content_is_not_cut(client: AsyncClient) -> None:
    token = await admin(client)
    await make_inquiry(client, content="짧은 문의")
    assert (await listing(client, token))["items"][0]["content_preview"] == "짧은 문의"


async def test_pagination(client: AsyncClient, db: async_sessionmaker[AsyncSession]) -> None:
    token = await admin(client)
    await make_in_order(client, db, [f"고객{index}" for index in range(5)])

    page1 = await listing(client, token, size=2, page=1)
    page3 = await listing(client, token, size=2, page=3)
    beyond = await listing(client, token, size=2, page=9)
    assert [i["name"] for i in page1["items"]] == ["고객4", "고객3"]
    assert [i["name"] for i in page3["items"]] == ["고객0"]
    assert page1["total_count"] == page3["total_count"] == 5
    assert beyond["items"] == [] and beyond["total_count"] == 5


async def test_same_created_at_never_repeats_or_skips_across_pages(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    token = await admin(client)
    same_time = datetime(2026, 11, 1, tzinfo=UTC)
    ids = []
    for _ in range(5):
        created = await make_inquiry(client)
        await set_created_at(db, created["inquiry_id"], same_time)
        ids.append(created["inquiry_id"])

    seen: list[str] = []
    for page in range(1, 6):
        seen += [i["id"] for i in (await listing(client, token, size=1, page=page))["items"]]
    assert sorted(seen) == sorted(ids) and len(set(seen)) == 5
    assert seen == sorted(ids, reverse=True)  # created_at이 같으면 id 내림차순


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"size": 0}, {"size": 101}, {"status": "done"}, {"origin": "walk_in"}],
)
async def test_list_rejects_bad_params(client: AsyncClient, params: dict) -> None:
    token = await admin(client)
    response = await client.get("/api/admin/inquiries", params=params, headers=token)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_filters_by_origin_and_viewed(client: AsyncClient, fake_rag: FakeRag) -> None:
    token = await admin(client)
    fake_rag.respond = lambda q, h: rag_response(mode="unknown", show_contact=True, sources=[])
    chat_id, chat_headers = await new_chat(client)
    turn = (await ask(client, chat_id, chat_headers))["body"]
    direct = await make_inquiry(client)
    await make_inquiry(
        client,
        chat_headers,
        origin="uncertain_answer_card",
        chat_id=chat_id,
        trigger_turn_id=turn["turn_id"],
    )
    await patch(client, token, direct["inquiry_id"], {"viewed": True})

    cards = await listing(client, token, origin="uncertain_answer_card")
    assert cards["total_count"] == 1 and cards["items"][0]["has_conversation"] is True
    assert (await listing(client, token, viewed="true"))["total_count"] == 1
    unread = await listing(client, token, viewed="false")
    assert unread["total_count"] == 1 and unread["items"][0]["is_unread"] is True
    assert (await listing(client, token, viewed="false", origin="direct_form"))["total_count"] == 0


async def test_period_is_from_inclusive_to_exclusive_and_naive_is_rejected(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    token = await admin(client)
    base = datetime(2026, 11, 10, tzinfo=UTC)
    for name, offset in (("전날", -1), ("당일 0시", 0), ("당일 오후", 12), ("다음날 0시", 24)):
        created = await make_inquiry(client, name=name)
        await set_created_at(db, created["inquiry_id"], base + timedelta(hours=offset))

    window = {"from": "2026-11-10T00:00:00Z", "to": "2026-11-11T00:00:00Z"}
    names = {i["name"] for i in (await listing(client, token, **window))["items"]}
    assert names == {"당일 0시", "당일 오후"}  # from 포함, to 미포함

    # 시간대 없는 값은 질문 로그·대시보드·답 못 한 질문과 같이 거절한다
    for path in ("/api/admin/inquiries", "/api/admin/inquiry-counts"):
        response = await client.get(
            path,
            params={"from": "2026-11-10T00:00:00"},
            headers=token,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    kst = {"from": "2026-11-10T09:00:00+09:00", "to": "2026-11-11T09:00:00+09:00"}
    assert (await listing(client, token, **kst))["total_count"] == 2
    assert (await listing(client, token, **{"from": "2026-11-10T12:00:00Z"}))["total_count"] == 2


@pytest.mark.parametrize("path", ["/api/admin/inquiries", "/api/admin/inquiry-counts"])
async def test_from_must_be_before_to(client: AsyncClient, path: str) -> None:
    token = await admin(client)
    same = {"from": "2026-11-10T00:00:00Z", "to": "2026-11-10T00:00:00Z"}
    reversed_ = {"from": "2026-11-11T00:00:00Z", "to": "2026-11-10T00:00:00Z"}
    for params in (same, reversed_):
        response = await client.get(path, params=params, headers=token)
        assert response.status_code == 422
        assert response.json()["error"]["fields"] == ["from", "to"]


# ---------- 건수 ----------


async def test_counts_by_status_and_unread(client: AsyncClient) -> None:
    token = await admin(client)
    assert await counts(client, token) == {
        "received": 0,
        "in_progress": 0,
        "completed": 0,
        "unresolved": 0,
        "unread": 0,
        "total": 0,
    }
    a = await make_inquiry(client)
    b = await make_inquiry(client)
    c = await make_inquiry(client)
    await make_inquiry(client)
    await patch(client, token, a["inquiry_id"], {"status": "in_progress", "viewed": True})
    await patch(client, token, b["inquiry_id"], {"status": "completed"})
    await patch(client, token, c["inquiry_id"], {"viewed": True})

    assert await counts(client, token) == {
        "received": 2,
        "in_progress": 1,
        "completed": 1,
        "unresolved": 3,  # received + in_progress
        "unread": 2,  # b(완료지만 읽지 않음)와 네 번째. 읽음은 상태와 별개다
        "total": 4,
    }


async def test_counts_match_list_totals_for_the_same_filter(
    client: AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    """목록 탭의 숫자와 목록의 총 건수가 같은 조건으로 같아야 한다."""
    token = await admin(client)
    statuses = ["received", "in_progress", "completed", "received", "completed"]
    for index, state in enumerate(statuses):
        created = await make_inquiry(client)
        await patch(client, token, created["inquiry_id"], {"status": state})
        await set_created_at(db, created["inquiry_id"], datetime(2026, 11, 1 + index, tzinfo=UTC))

    window = {"from": "2026-11-02T00:00:00Z", "to": "2026-11-05T00:00:00Z"}
    summary = await counts(client, token, **window)
    for state in ("received", "in_progress", "completed", "unresolved", "all"):
        total = (await listing(client, token, status=state, **window))["total_count"]
        expected = summary["total"] if state == "all" else summary[state]
        assert total == expected, state
    assert summary["total"] == 3


async def test_counts_filter_by_origin(client: AsyncClient) -> None:
    token = await admin(client)
    await make_inquiry(client)
    chat_id, chat_headers = await new_chat(client)
    await make_inquiry(client, chat_headers, origin="agent_request", chat_id=chat_id)

    assert (await counts(client, token, origin="agent_request"))["total"] == 1
    assert (await counts(client, token, origin="uncertain_answer_card"))["total"] == 0
    assert (await counts(client, token))["total"] == 2


# ---------- 상세와 채팅 기록 ----------


async def test_detail_of_direct_inquiry_has_no_conversation(client: AsyncClient) -> None:
    token = await admin(client)
    created = await make_inquiry(client, email="hong@example.com", content="전문 내용입니다.")

    body = await detail(client, token, created["inquiry_id"])
    assert body["reference_no"] == created["reference_no"] == "INQ-1001"
    assert body["email"] == "hong@example.com" and body["content"] == "전문 내용입니다."
    assert body["conversation"] == [] and body["chat_id"] is None
    assert body["trigger_turn_id"] is None and body["has_conversation"] is False
    assert body["internal_note"] == "" and body["completed_at"] is None
    assert body["first_viewed_at"] is None and body["is_unread"] is True


async def test_viewing_detail_never_marks_it_read(client: AsyncClient) -> None:
    token = await admin(client)
    created = await make_inquiry(client)
    for _ in range(3):
        body = await detail(client, token, created["inquiry_id"])
    assert body["first_viewed_at"] is None and body["is_unread"] is True
    assert (await counts(client, token))["unread"] == 1


async def test_detail_shows_chat_with_sources_and_trigger(
    client: AsyncClient, fake_rag: FakeRag
) -> None:
    token = await admin(client)
    chat_id, chat_headers = await new_chat(client)
    await ask(client, chat_id, chat_headers, "충전은 어떻게 하나요?")
    fake_rag.respond = lambda q, h: rag_response(
        mode="unknown",
        answer="자료에서 확인되지 않아요.",
        sources=[],
        show_contact=True,
        retrieved_ids=["Q01", "Q02", "P01", "Q99"],
        retrieved_scores=[0.4, 0.3, 0.2, 0.1],
    )
    second = (await ask(client, chat_id, chat_headers, "우주선도 파나요?"))["body"]
    created = await make_inquiry(
        client,
        chat_headers,
        origin="uncertain_answer_card",
        chat_id=chat_id,
        trigger_turn_id=second["turn_id"],
    )

    body = await detail(client, token, created["inquiry_id"])
    assert body["chat_id"] == chat_id and body["trigger_turn_id"] == second["turn_id"]
    assert body["has_conversation"] is True
    first_turn, trigger_turn = body["conversation"]  # 오래된 순
    assert first_turn["question"] == "충전은 어떻게 하나요?" and first_turn["is_trigger"] is False
    assert first_turn["mode"] == "answer" and first_turn["status"] == "completed"
    assert first_turn["cited_sources"] == [
        {"rank": 1, "source_id": "Q02", "title": "충전은 어떻게 하나요?", "score": 0.8}
    ]
    assert trigger_turn["turn_id"] == second["turn_id"] and trigger_turn["is_trigger"] is True
    # 답변 불가 turn은 근거가 비어 있고, 어떤 FAQ 근처였는지는 검색 후보 상위 3개로 본다
    assert trigger_turn["mode"] == "unknown" and trigger_turn["cited_sources"] == []
    assert [s["source_id"] for s in trigger_turn["retrieved_sources"]] == ["Q01", "Q02", "P01"]
    assert [s["rank"] for s in trigger_turn["retrieved_sources"]] == [1, 2, 3]


async def test_chat_after_the_inquiry_is_not_added(client: AsyncClient) -> None:
    token = await admin(client)
    chat_id, chat_headers = await new_chat(client)
    first = (await ask(client, chat_id, chat_headers, "첫 질문"))["body"]
    created = await make_inquiry(
        client, chat_headers, chat_id=chat_id, trigger_turn_id=first["turn_id"]
    )
    before = await detail(client, token, created["inquiry_id"])

    await ask(client, chat_id, chat_headers, "문의 뒤에 이어진 질문", first["turn_id"])
    after = await detail(client, token, created["inquiry_id"])
    assert [t["question"] for t in before["conversation"]] == ["첫 질문"]
    assert after["conversation"] == before["conversation"]  # 다시 조회해도 늘어나지 않는다


async def test_failed_turn_stays_in_the_record(client: AsyncClient, fake_rag: FakeRag) -> None:
    token = await admin(client)
    fake_rag.respond = lambda q, h: RuntimeError("llm down")
    chat_id, chat_headers = await new_chat(client)
    failed = await ask(client, chat_id, chat_headers, "장애 중 질문")
    assert failed["status"] == 503
    created = await make_inquiry(client, chat_headers, chat_id=chat_id)

    body = await detail(client, token, created["inquiry_id"])
    (turn,) = body["conversation"]
    assert turn["status"] == "failed" and turn["question"] == "장애 중 질문"
    assert turn["mode"] is None and turn["answer"] is None and turn["cited_sources"] == []
    assert body["has_conversation"] is True and body["trigger_turn_id"] is None


async def test_agent_request_before_any_question_has_empty_record(client: AsyncClient) -> None:
    token = await admin(client)
    chat_id, chat_headers = await new_chat(client)
    created = await make_inquiry(client, chat_headers, origin="agent_request", chat_id=chat_id)

    body = await detail(client, token, created["inquiry_id"])
    # 대화는 있지만 저장된 turn이 없어 채팅 기록은 비어 있다
    assert body["chat_id"] == chat_id and body["conversation"] == []
    assert body["has_conversation"] is False
    item = (await listing(client, token))["items"][0]
    assert item["has_conversation"] is False


async def test_branched_attempts_are_both_listed(client: AsyncClient) -> None:
    token = await admin(client)
    chat_id, chat_headers = await new_chat(client)
    one = (await ask(client, chat_id, chat_headers, "같은 질문"))["body"]
    two = (await ask(client, chat_id, chat_headers, "같은 질문"))["body"]  # 다시 답변받기
    created = await make_inquiry(
        client, chat_headers, chat_id=chat_id, trigger_turn_id=two["turn_id"]
    )

    turns = (await detail(client, token, created["inquiry_id"]))["conversation"]
    assert [t["turn_id"] for t in turns] == [one["turn_id"], two["turn_id"]]
    assert turns[0]["parent_turn_id"] is None and turns[1]["parent_turn_id"] is None


async def test_unknown_inquiry_is_404(client: AsyncClient) -> None:
    token = await admin(client)
    missing = str(uuid.uuid4())
    for response in (
        await client.get(f"/api/admin/inquiries/{missing}", headers=token),
        await client.patch(f"/api/admin/inquiries/{missing}", json={"viewed": True}, headers=token),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    bad = await client.get("/api/admin/inquiries/not-a-uuid", headers=token)
    assert bad.status_code == 422


# ---------- 수정 ----------


async def test_viewed_records_only_the_first_time_and_keeps_status(client: AsyncClient) -> None:
    token = await admin(client)
    created = await make_inquiry(client)
    iid = created["inquiry_id"]

    status, first = await patch(client, token, iid, {"viewed": True})
    assert status == 200
    assert first["first_viewed_at"] is not None and first["is_unread"] is False
    assert first["status"] == "received"  # 읽음 처리는 상태를 바꾸지 않는다

    status, again = await patch(client, token, iid, {"viewed": True})
    assert again["first_viewed_at"] == first["first_viewed_at"]
    assert again["updated_at"] == first["updated_at"]  # 바뀐 게 없으면 수정 시각도 그대로
    assert (await listing(client, token, viewed="true"))["total_count"] == 1


async def test_status_changes_set_and_clear_completed_at(client: AsyncClient) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]

    _, in_progress = await patch(client, token, iid, {"status": "in_progress"})
    assert in_progress["status"] == "in_progress" and in_progress["completed_at"] is None

    _, done = await patch(client, token, iid, {"status": "completed"})
    assert done["completed_at"] is not None

    _, saved_again = await patch(client, token, iid, {"status": "completed"})
    assert saved_again["completed_at"] == done["completed_at"]  # 같은 완료 재저장은 시각 유지
    assert saved_again["updated_at"] == done["updated_at"]

    _, reopened = await patch(client, token, iid, {"status": "received"})
    assert reopened["status"] == "received" and reopened["completed_at"] is None  # 되돌리면 지운다
    assert reopened["is_unread"] is True  # 상태를 바꿔도 읽음 여부는 그대로다


async def test_internal_note_save_replace_clear(client: AsyncClient) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]

    _, saved = await patch(client, token, iid, {"internal_note": "배송사에 확인 요청함"})
    assert saved["internal_note"] == "배송사에 확인 요청함"
    _, replaced = await patch(client, token, iid, {"internal_note": "확인 완료, 내일 회신"})
    assert replaced["internal_note"] == "확인 완료, 내일 회신"  # 마지막 저장이 남는다
    _, cleared = await patch(client, token, iid, {"internal_note": ""})
    assert cleared["internal_note"] == ""
    assert (await detail(client, token, iid))["internal_note"] == ""

    _, longest = await patch(client, token, iid, {"internal_note": "가" * 2000})
    assert len(longest["internal_note"]) == 2000


async def test_patch_can_change_several_fields_at_once(client: AsyncClient) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]

    status, body = await patch(
        client, token, iid, {"viewed": True, "status": "in_progress", "internal_note": "접수 확인"}
    )
    assert status == 200
    assert body["status"] == "in_progress" and body["internal_note"] == "접수 확인"
    assert body["is_unread"] is False
    assert body == await detail(client, token, iid)  # 응답이 상세 조회와 같다


async def test_status_change_bumps_updated_at(client: AsyncClient) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]
    before = await detail(client, token, iid)
    _, after = await patch(client, token, iid, {"status": "in_progress"})
    assert after["updated_at"] > before["updated_at"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"viewed": False},
        {"viewed": None},
        {"status": "bogus"},
        {"status": None},
        {"internal_note": None},
        {"internal_note": "가" * 2001},
        {"unknown_field": 1},
        {"viewed": True, "unknown_field": 1},
    ],
    ids=[
        "empty",
        "viewed-false",
        "viewed-null",
        "bad-status",
        "status-null",
        "note-null",
        "note-too-long",
        "unknown-field",
        "valid-plus-unknown",
    ],
)
async def test_patch_rejects_bad_bodies_without_changing_anything(
    client: AsyncClient, body: dict
) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]
    before = await detail(client, token, iid)

    status, response = await patch(client, token, iid, body)
    assert status == 422 and response["error"]["code"] == "validation_error"
    assert await detail(client, token, iid) == before


async def test_two_simultaneous_read_marks_keep_the_first_time(client: AsyncClient) -> None:
    token = await admin(client)
    iid = (await make_inquiry(client))["inquiry_id"]

    results = await asyncio.gather(*(patch(client, token, iid, {"viewed": True}) for _ in range(4)))
    stamps = {body["first_viewed_at"] for _, body in results}
    assert all(status == 200 for status, _ in results)
    assert len(stamps) == 1  # 모두 같은 최초 읽음 시각을 본다
    assert (await detail(client, token, iid))["first_viewed_at"] == stamps.pop()


async def test_admin_changes_are_invisible_to_the_customer_api(client: AsyncClient) -> None:
    token = await admin(client)
    request_id = str(uuid.uuid4())
    payload = {
        "name": "데모 고객",
        "email": "demo@example.com",
        "content": "한쪽만 따로 살 수 있나요?",
        "origin": "direct_form",
        "request_id": request_id,
    }
    created = (await client.post("/api/inquiries", json=payload)).json()
    await patch(
        client,
        token,
        created["inquiry_id"],
        {"internal_note": "고객에게 보이면 안 되는 메모", "status": "completed", "viewed": True},
    )

    replay = (await client.post("/api/inquiries", json=payload)).json()
    # 같은 요청을 다시 보내도 고객 응답에는 접수 정보 4개만 있고 메모·읽음 정보가 없다
    assert set(replay) == {"inquiry_id", "reference_no", "status", "created_at"}
    assert "고객에게 보이면 안 되는 메모" not in str(replay)
