"""DB 없이 확인하는 규칙: 한국 날짜 경계, 요청 제한, 로그인 차단, RAG 장애 알림."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.rate_limit import (
    LoginGuard,
    SlidingWindowLimiter,
    kst_day_start,
    seconds_until_kst_midnight,
)
from rag.errors import ParseError, RetrievalError
from rag.glossary import normalize
from rag.pipeline import (
    Decision,
    LlmResult,
    LlmResultWithGreeting,
    LlmResultWithHandoff,
    RagPipeline,
    select_schema,
)
from rag.schemas import Source


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_kst_day_boundary() -> None:
    # UTC 14:59는 한국 23:59, UTC 15:00은 한국 다음 날 0시
    before = datetime(2026, 11, 13, 14, 59, tzinfo=UTC)
    after = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
    assert kst_day_start(before) == datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    assert kst_day_start(after) == datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
    assert seconds_until_kst_midnight(before) == 60
    assert seconds_until_kst_midnight(after) == 24 * 3600


def test_limiter_window_and_retry_after() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)
    assert limiter.hit("k", 2, 60) is None
    assert limiter.hit("k", 2, 60) is None
    clock.now += 10
    assert limiter.hit("k", 2, 60) == 50
    clock.now += 50
    assert limiter.hit("k", 2, 60) is None


def test_limiter_cleanup_keeps_longer_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.rate_limit.MAX_KEYS_BEFORE_CLEANUP", 2)
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock)
    assert limiter.hit("inquiry", 1, 3600) is None
    clock.now += 120
    # 1분 창 요청이 정리를 일으켜도 1시간 창 기록은 남아야 한다
    limiter.hit("a", 1, 60)
    limiter.hit("b", 1, 60)
    assert limiter.hit("inquiry", 1, 3600) is not None


def test_login_guard_locks_per_ip_and_expires() -> None:
    clock = FakeClock()
    guard = LoginGuard(max_failures=2, lockout_seconds=900, clock=clock)
    guard.fail("a")
    guard.fail("a")
    assert guard.blocked_for("a") == 900
    assert guard.blocked_for("b") is None
    clock.now += 901
    assert guard.blocked_for("a") is None


def test_login_guard_success_resets_failures() -> None:
    guard = LoginGuard(max_failures=2, lockout_seconds=900, clock=FakeClock())
    guard.fail("a")
    guard.succeed("a")
    guard.fail("a")
    assert guard.blocked_for("a") is None


def test_unparsed_llm_response_is_failure_not_unknown() -> None:
    with pytest.raises(ParseError):
        RagPipeline._check(None, [])


async def test_retrieval_failure_keeps_cause() -> None:
    pipeline = object.__new__(RagPipeline)
    cause = ConnectionError("qdrant down")

    async def broken(question: str, previous: list[str]) -> list:
        raise cause

    pipeline._retrieve = broken
    with pytest.raises(RetrievalError) as caught:
        await pipeline._decide("질문", [])
    assert caught.value.__cause__ is cause


def _handoff_result(verdict: str, answer: str, needs_agent: bool = True) -> LlmResultWithHandoff:
    return LlmResultWithHandoff(
        reason="r", verdict=verdict, needs_agent=needs_agent, faq_ids=[], answer=answer
    )


def test_handoff_is_unknown_with_empathy_kept() -> None:
    decision = RagPipeline._check(_handoff_result("handoff", "불편을 드려 죄송합니다."), [])
    assert (decision.mode, decision.handoff) == ("unknown", True)
    assert decision.answer == "불편을 드려 죄송합니다."
    assert decision.reason.startswith("상담 연결 요청")


def test_handoff_empathy_with_numbers_or_too_long_falls_back() -> None:
    # 공감 문장에 숫자(제품 사실·약속)가 섞이거나 길면 고정 문구만 쓰게 비운다
    with_number = RagPipeline._check(_handoff_result("handoff", "3일 안에 환불해 드릴게요."), [])
    too_long = RagPipeline._check(_handoff_result("handoff", "죄송합니다. " * 30), [])
    # 연락처는 고정 안내에만 둔다. 숫자 없는 이메일을 지어내도 막는다
    with_email = RagPipeline._check(
        _handoff_result("handoff", "help@example.com로 연락 주세요."), []
    )
    assert with_number.answer is None
    assert too_long.answer is None
    assert with_email.answer is None


def test_handoff_message_joins_guide_or_uses_fallback() -> None:
    pipeline = object.__new__(RagPipeline)
    pipeline.prompts = {"handoff_guide": "안내\n", "handoff_message": "전체 문구\n"}
    assert pipeline._handoff_message("죄송합니다.") == "죄송합니다.\n안내"
    assert pipeline._handoff_message(None) == "전체 문구"


def test_needs_agent_kept_for_offtopic() -> None:
    decision = RagPipeline._check(_handoff_result("offtopic", ""), [])
    assert (decision.mode, decision.needs_agent, decision.handoff) == ("offtopic", True, False)


def test_schema_follows_prompt_keys() -> None:
    # 상담 연결 문구가 없는 기존 프롬프트는 예전 판단 범위를 그대로 쓴다
    assert select_schema({"handoff_message": "", "handoff_guide": ""}) is LlmResultWithHandoff
    assert select_schema({"handoff_message": ""}) is not LlmResultWithHandoff
    assert select_schema({"greeting_message": ""}) is LlmResultWithGreeting
    assert select_schema({}) is LlmResult


async def test_needs_agent_shows_contact_even_after_number_fallback() -> None:
    pipeline = object.__new__(RagPipeline)
    pipeline.config = SimpleNamespace(
        retrieval=SimpleNamespace(history_turns=0),
        decision=SimpleNamespace(verify_numbers=True),
        generation=SimpleNamespace(contact_email=None),
    )
    pipeline.retriever = SimpleNamespace(support_required_ids=set())
    source = Source(faq_id="Q1", title="질문", category="c", score=0.9, excerpt="원문 답변")

    async def decide(question: str, previous: list[str]) -> Decision:
        # FAQ에 없는 숫자(99)를 넣어 원문 대체 경로를 탄다
        return Decision("answer", [source], "r", "불편을 드려 죄송합니다. 99분", needs_agent=True)

    pipeline._decide = decide
    response = await pipeline.aanswer("질문")
    assert response.answer == "원문 답변"
    assert response.show_contact is True


def test_glossary_only_rewrites_person_connection_requests() -> None:
    # 대상 없는 "연결해 주세요"는 블루투스·앱 연결 질문에도 나오므로 바꾸지 않는다
    # "사람"은 "두 사람", "다른 사람과"처럼 인원을 말할 때도 쓰이므로 바꾸지 않는다
    for question in (
        "블루투스 매번 연결해줘야 하나요?",
        "폰이랑 연결해 주세요 어떻게 해요",
        "두 사람 연결돼요?",
        "다른 사람과 연결해서 같이 들을 수 있나요",
    ):
        assert normalize(question, "default") == question
    assert "상담원 1:1 문의" in normalize("담당자하고 바로 연결해줘", "default")


def test_limiter_counts_same_request_once() -> None:
    limiter = SlidingWindowLimiter(FakeClock())
    assert limiter.hit("k", 1, 3600, request_key="r1") is None
    assert limiter.hit("k", 1, 3600, request_key="r1") is None
    assert limiter.hit("k", 1, 3600, request_key="r2") is not None
