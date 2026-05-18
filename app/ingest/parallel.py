"""병렬 임베딩 — Sprint 7 (Pillar 5).

asyncio.Semaphore 로 동시 요청 수를 제한하면서 처리량을 높인다.
임베딩 함수 시그니처는 ``async def embed(text: str) -> list[float]``.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable, Sequence


async def bounded_gather(
    coros: Iterable[Awaitable], *, limit: int = 8
) -> list:
    """asyncio.gather + Semaphore. 결과 순서는 입력 순서와 동일."""
    sem = asyncio.Semaphore(max(1, limit))

    async def _wrapped(coro: Awaitable):
        async with sem:
            return await coro

    return await asyncio.gather(*[_wrapped(c) for c in coros])


async def parallel_embed(
    texts: Sequence[str],
    embed_fn: Callable[[str], Awaitable[list[float]]],
    *,
    concurrency: int = 8,
) -> list[list[float]]:
    """배치 단위 병렬 임베딩.

    실패 시 해당 슬롯은 ``[]`` 로 채워, 호출 측이 quality gate 에서 결정한다.
    """
    if not texts:
        return []

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(text: str) -> list[float]:
        async with sem:
            try:
                return list(await embed_fn(text))
            except Exception:  # noqa: BLE001
                return []

    return await asyncio.gather(*[_one(t) for t in texts])


__all__ = ["bounded_gather", "parallel_embed"]
