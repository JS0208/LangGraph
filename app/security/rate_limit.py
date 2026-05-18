"""Rate limit — Sprint 7 (Pillar 7 보강).

목적
- ``slowapi`` 또는 Redis 의존 없이도 IP/사용자별 요청률을 제한.
- token bucket: 초당 X token 충전, 버킷 크기 = burst.

사용 예
```python
limiter = get_rate_limiter()
key = f"ip:{request.client.host}"
if not limiter.allow(key):
    raise HTTPException(429, "rate limit")
```

테스트는 ``time_provider`` 를 주입해 결정론적으로 검증한다.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.observability.metrics import counter_inc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """다중 키 동시 token bucket.

    - ``rate_per_sec``: 초당 충전 토큰 수
    - ``burst``: 한 번에 가능한 최대 토큰 (=버킷 크기)
    - ``cost``: 한 번 ``allow`` 호출에 차감할 토큰
    """

    def __init__(
        self,
        *,
        rate_per_sec: float | None = None,
        burst: float | None = None,
        cost: float = 1.0,
        time_provider: Callable[[], float] = time.time,
    ) -> None:
        self._rate = float(rate_per_sec or _env_float("RATE_LIMIT_PER_SEC", 5.0))
        self._burst = float(burst or _env_float("RATE_LIMIT_BURST", 10.0))
        self._cost = float(cost)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._time = time_provider

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = max(0.0, now - bucket.last_refill)
        bucket.tokens = min(self._burst, bucket.tokens + elapsed * self._rate)
        bucket.last_refill = now

    def allow(self, key: str, *, cost: float | None = None) -> bool:
        if not key:
            return True
        c = self._cost if cost is None else float(cost)
        now = self._time()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._burst, last_refill=now)
                self._buckets[key] = bucket
            self._refill(bucket, now)
            if bucket.tokens >= c:
                bucket.tokens -= c
                counter_inc("rate_limit_allowed_total", 1.0)
                return True
            counter_inc("rate_limit_throttled_total", 1.0)
            return False

    def remaining(self, key: str) -> float:
        if not key:
            return self._burst
        now = self._time()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return self._burst
            self._refill(bucket, now)
            return bucket.tokens

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


_default_limiter: TokenBucketRateLimiter | None = None


def get_rate_limiter() -> TokenBucketRateLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = TokenBucketRateLimiter()
    return _default_limiter


def set_rate_limiter(limiter: TokenBucketRateLimiter | None) -> None:
    global _default_limiter
    _default_limiter = limiter


__all__ = [
    "TokenBucketRateLimiter",
    "get_rate_limiter",
    "set_rate_limiter",
]
