"""DB 없이 확인하는 규칙: 한국 날짜 경계, 요청 제한, 로그인 차단, RAG 장애 알림."""

from datetime import UTC, datetime

import pytest

from app.core.rate_limit import (
    LoginGuard,
    SlidingWindowLimiter,
    kst_day_start,
    seconds_until_kst_midnight,
)
from rag.errors import ParseError, RetrievalError
from rag.pipeline import RagPipeline


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


def test_limiter_counts_same_request_once() -> None:
    limiter = SlidingWindowLimiter(FakeClock())
    assert limiter.hit("k", 1, 3600, request_key="r1") is None
    assert limiter.hit("k", 1, 3600, request_key="r1") is None
    assert limiter.hit("k", 1, 3600, request_key="r2") is not None
