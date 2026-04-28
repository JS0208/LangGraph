"""의존성 0 의 Circuit Breaker — Sprint 6.

상태
- ``closed``: 정상 (호출 통과)
- ``open``: 차단 (호출 즉시 ``CircuitOpenError``). ``recovery_time_s`` 후 half_open 으로.
- ``half_open``: 1회 호출만 허용. 성공 시 closed, 실패 시 open 으로 회귀.

스레드 안전. 비동기 코드에서 ``call(fn)`` 으로 감싸 사용한다.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """차단된 회로에서 호출 시도 시 발생."""


@dataclass
class _State:
    name: str = "closed"  # closed | open | half_open
    failure_count: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_time_s: float = 30.0,
    ) -> None:
        self.name = name
        self._failure_threshold = max(1, int(failure_threshold))
        self._recovery_time_s = float(recovery_time_s)
        self._state = _State()
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_recover()
            return self._state.name

    def _maybe_recover(self) -> None:
        s = self._state
        if s.name == "open" and (time.time() - s.opened_at) >= self._recovery_time_s:
            s.name = "half_open"

    def _on_success(self) -> None:
        with self._lock:
            self._state = _State()  # reset

    def _on_failure(self) -> None:
        with self._lock:
            s = self._state
            if s.name == "half_open":
                s.name = "open"
                s.opened_at = time.time()
                return
            s.failure_count += 1
            if s.failure_count >= self._failure_threshold:
                s.name = "open"
                s.opened_at = time.time()

    def reset(self) -> None:
        with self._lock:
            self._state = _State()

    async def acall(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        with self._lock:
            self._maybe_recover()
            if self._state.name == "open":
                raise CircuitOpenError(f"circuit '{self.name}' is open")
        try:
            result = await fn(*args, **kwargs)
        except BaseException:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result


__all__ = ["CircuitBreaker", "CircuitOpenError"]
