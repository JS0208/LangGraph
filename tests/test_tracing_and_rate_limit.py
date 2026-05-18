"""Sprint 7 — OTel-style tracing shim + rate limit 단위 테스트."""

from __future__ import annotations

import asyncio

from app.observability.tracing import collector, reset_traces, start_span
from app.security.rate_limit import TokenBucketRateLimiter


def test_start_span_records_to_collector():
    reset_traces()

    async def _go():
        async with start_span("outer", attrs={"intent": "facts"}) as outer:
            assert outer.name == "outer"
            async with start_span("inner") as inner:
                assert inner.parent_id == outer.span_id

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_go())
    finally:
        loop.close()

    snap = collector().snapshot()
    names = {s["name"] for s in snap}
    assert {"outer", "inner"}.issubset(names)
    inner = next(s for s in snap if s["name"] == "inner")
    assert inner["parent_id"] is not None
    assert inner["status"] == "ok"


def test_start_span_records_error_status():
    reset_traces()

    async def _go():
        try:
            async with start_span("failing"):
                raise ValueError("boom")
        except ValueError:
            pass

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_go())
    finally:
        loop.close()
    snap = collector().snapshot()
    failing = [s for s in snap if s["name"] == "failing"][-1]
    assert failing["status"] == "error"
    assert failing["error"] == "boom"


def test_token_bucket_rate_limiter_blocks_when_empty():
    now = [0.0]
    limiter = TokenBucketRateLimiter(
        rate_per_sec=1.0,
        burst=2.0,
        cost=1.0,
        time_provider=lambda: now[0],
    )
    assert limiter.allow("ip:1.2.3.4") is True
    assert limiter.allow("ip:1.2.3.4") is True
    # 버킷 소진
    assert limiter.allow("ip:1.2.3.4") is False
    # 1초 경과 시 1 토큰 충전
    now[0] += 1.0
    assert limiter.allow("ip:1.2.3.4") is True


def test_rate_limiter_independent_keys():
    now = [0.0]
    limiter = TokenBucketRateLimiter(rate_per_sec=1.0, burst=1.0, time_provider=lambda: now[0])
    assert limiter.allow("ip:a") is True
    # ip:a 는 소진, ip:b 는 영향 없음
    assert limiter.allow("ip:a") is False
    assert limiter.allow("ip:b") is True
