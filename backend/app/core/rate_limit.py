"""분 단위 요청 제한(메모리)과 하루 한도 계산에 쓰는 한국 날짜 경계.

메모리 제한은 서버를 재시작하면 초기화되고, 인스턴스가 여러 개면 인스턴스마다 따로 센다.
피해가 작아서 허용한다. 하루 한도는 DB 행 수로 센다(Service 참고).
"""

import math
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

# 한국은 서머타임이 없어 고정 오프셋으로 충분하다
KST = timezone(timedelta(hours=9))
# 키가 이 수를 넘으면 오래된 기록을 정리한다
MAX_KEYS_BEFORE_CLEANUP = 10_000

Clock = Callable[[], float]


class SlidingWindowLimiter:
    """키마다 최근 window_seconds 동안의 요청 시각을 기억한다."""

    def __init__(self, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        # 키 → (창 길이, (요청 시각, 요청 ID)들). 정리할 때 키마다 자기 창 길이로 판단한다
        self._hits: dict[str, tuple[float, deque[tuple[float, str | None]]]] = {}

    def hit(
        self, key: str, limit: int, window_seconds: float, request_key: str | None = None
    ) -> int | None:
        """요청 한 번을 센다. 한도를 넘으면 기록하지 않고 다시 시도까지 남은 초를 돌려준다.

        request_key가 같은 요청(같은 문의의 재전송)은 창 안에서 한 번만 센다.
        """
        now = self._clock()
        _, hits = self._hits.setdefault(key, (window_seconds, deque()))
        while hits and hits[0][0] <= now - window_seconds:
            hits.popleft()
        if request_key is not None and any(seen == request_key for _, seen in hits):
            return None
        if len(hits) >= limit:
            return max(1, math.ceil(hits[0][0] + window_seconds - now))
        hits.append((now, request_key))
        if len(self._hits) > MAX_KEYS_BEFORE_CLEANUP:
            self._cleanup(now)
        return None

    def _cleanup(self, now: float) -> None:
        stale = [
            key
            for key, (window, hits) in self._hits.items()
            if not hits or hits[-1][0] <= now - window
        ]
        for key in stale:
            del self._hits[key]


class LoginGuard:
    """관리자 로그인 연속 실패를 IP별로 센다. 계정 기준으로 막으면 누구나 관리자를 잠글 수 있다."""

    def __init__(
        self, max_failures: int, lockout_seconds: float, clock: Clock = time.monotonic
    ) -> None:
        self._max = max_failures
        self._lockout = lockout_seconds
        self._clock = clock
        # IP → (연속 실패 수, 마지막 실패 시각)
        self._failures: dict[str, tuple[int, float]] = {}
        self._locked_until: dict[str, float] = {}

    def blocked_for(self, key: str) -> int | None:
        until = self._locked_until.get(key)
        if until is None:
            return None
        left = until - self._clock()
        if left <= 0:
            del self._locked_until[key]
            return None
        return max(1, math.ceil(left))

    def fail(self, key: str) -> None:
        now = self._clock()
        count = self._failures.get(key, (0, now))[0] + 1
        if count >= self._max:
            self._locked_until[key] = now + self._lockout
            self._failures.pop(key, None)
        else:
            self._failures[key] = (count, now)
        if len(self._failures) + len(self._locked_until) > MAX_KEYS_BEFORE_CLEANUP:
            self._cleanup(now)

    def succeed(self, key: str) -> None:
        self._failures.pop(key, None)

    def _cleanup(self, now: float) -> None:
        # 차단 시간만큼 지난 실패 기록과 끝난 차단은 지운다
        self._failures = {k: v for k, v in self._failures.items() if v[1] > now - self._lockout}
        self._locked_until = {k: v for k, v in self._locked_until.items() if v > now}


def kst_day_start(now: datetime | None = None) -> datetime:
    """지금이 속한 한국 날짜의 0시를 UTC로 돌려준다."""
    local = (now or datetime.now(UTC)).astimezone(KST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def seconds_until_kst_midnight(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    next_midnight = kst_day_start(current) + timedelta(days=1)
    return max(1, math.ceil((next_midnight - current).total_seconds()))
