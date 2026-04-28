"""통일 retry 정책 — Sprint 1.

설계 원칙
- ``tenacity`` 를 우선 사용하되, 미설치 환경(예: 최소 fallback 데모)에서도
  동일 시그니처로 동작하는 단순 백오프 루프를 fallback 으로 제공한다.
- 5xx / 429 / network 에러만 재시도하며, 4xx(<429)는 즉시 실패시킨다.
- 모든 호출 측은 이 모듈만 사용하도록 강제한다 (`llm_structured.py`, `real_clients.py`).
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_JITTER = 0.2  # ±20%


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


try:  # 우선 경로
    from tenacity import (
        AsyncRetrying,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    _HAS_TENACITY = True
except ImportError:  # 미설치 환경 fallback
    _HAS_TENACITY = False


def _compute_delay(attempt: int, base: float, max_delay: float, jitter: float) -> float:
    """Exponential backoff with symmetric jitter (±jitter)."""
    raw = base * (2 ** (attempt - 1))
    capped = min(raw, max_delay)
    jitter_band = capped * jitter
    return max(0.0, capped + random.uniform(-jitter_band, jitter_band))


async def _async_fallback_retry(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
    on_retry: Callable[[int, BaseException], None] | None,
    **kwargs: Any,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_retryable_http_error(exc) or attempt == max_attempts:
                raise
            delay = _compute_delay(attempt, base_delay, max_delay, jitter)
            if on_retry is not None:
                try:
                    on_retry(attempt, exc)
                except Exception:  # 콜백 실패가 본 흐름을 망가뜨리면 안 된다.
                    logger.warning("retry callback raised", exc_info=True)
            logger.info(
                "retrying (attempt %d/%d) in %.2fs after %s",
                attempt,
                max_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None  # 논리적으로 도달하지 않음
    raise last_exc


def async_retry(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """비동기 함수에 통일 재시도 정책을 적용하는 데코레이터.

    예::

        @async_retry(max_attempts=3)
        async def call_llm(...) -> dict: ...
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        if _HAS_TENACITY:

            @wraps(fn)
            async def tenacity_wrapper(*args: Any, **kwargs: Any) -> T:
                retrier = AsyncRetrying(
                    reraise=True,
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential_jitter(initial=base_delay, max=max_delay, jitter=base_delay * jitter),
                    retry=retry_if_exception(_is_retryable_http_error),
                )
                async for attempt in retrier:
                    with attempt:
                        if on_retry is not None and attempt.retry_state.attempt_number > 1:
                            outcome = attempt.retry_state.outcome
                            if outcome is not None and outcome.failed:
                                try:
                                    on_retry(attempt.retry_state.attempt_number, outcome.exception())  # type: ignore[arg-type]
                                except Exception:
                                    logger.warning("retry callback raised", exc_info=True)
                        return await fn(*args, **kwargs)
                # 도달 불가 (reraise=True)
                raise RuntimeError("unreachable")

            return tenacity_wrapper

        @wraps(fn)
        async def fallback_wrapper(*args: Any, **kwargs: Any) -> T:
            return await _async_fallback_retry(
                fn,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                on_retry=on_retry,
                **kwargs,
            )

        return fallback_wrapper

    return decorator


__all__ = [
    "async_retry",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_BASE_DELAY",
    "DEFAULT_MAX_DELAY",
    "DEFAULT_JITTER",
]
