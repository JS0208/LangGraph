from __future__ import annotations

import asyncio

import httpx
import pytest

from app.utils.retry import async_retry


def _make_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://example.test/x")
    response = httpx.Response(status_code=status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_async_retry_retries_on_5xx_then_succeeds():
    attempts = {"n": 0}

    @async_retry(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)
    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise _make_status_error(503)
        return "ok"

    result = asyncio.run(flaky())
    assert result == "ok"
    assert attempts["n"] == 2


def test_async_retry_does_not_retry_on_4xx():
    attempts = {"n": 0}

    @async_retry(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)
    async def fn():
        attempts["n"] += 1
        raise _make_status_error(400)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(fn())
    assert attempts["n"] == 1


def test_async_retry_retries_on_429_until_max_attempts():
    attempts = {"n": 0}

    @async_retry(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)
    async def fn():
        attempts["n"] += 1
        raise _make_status_error(429)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(fn())
    assert attempts["n"] == 3


def test_async_retry_retries_on_network_error():
    attempts = {"n": 0}

    @async_retry(max_attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0)
    async def fn():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ConnectError("network down")
        return 42

    assert asyncio.run(fn()) == 42
    assert attempts["n"] == 2
