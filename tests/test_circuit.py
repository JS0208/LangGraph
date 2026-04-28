from __future__ import annotations

import asyncio

import pytest

from app.utils.circuit import CircuitBreaker, CircuitOpenError


async def _raise():
    raise RuntimeError("boom")


async def _ok():
    return 42


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(name="t", failure_threshold=3, recovery_time_s=10.0)

    async def run():
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.acall(_raise)
        with pytest.raises(CircuitOpenError):
            await cb.acall(_ok)

    asyncio.run(run())
    assert cb.state == "open"


def test_circuit_recovers_to_half_open_then_closed():
    cb = CircuitBreaker(name="t2", failure_threshold=1, recovery_time_s=0.05)

    async def run():
        with pytest.raises(RuntimeError):
            await cb.acall(_raise)
        # open 상태
        with pytest.raises(CircuitOpenError):
            await cb.acall(_ok)
        # 회복 시간 경과
        await asyncio.sleep(0.06)
        # half_open 진입 후 성공 호출 시 closed 로 회귀
        result = await cb.acall(_ok)
        assert result == 42

    asyncio.run(run())
    assert cb.state == "closed"


def test_circuit_half_open_failure_returns_to_open():
    cb = CircuitBreaker(name="t3", failure_threshold=1, recovery_time_s=0.05)

    async def run():
        with pytest.raises(RuntimeError):
            await cb.acall(_raise)
        await asyncio.sleep(0.06)
        with pytest.raises(RuntimeError):
            await cb.acall(_raise)

    asyncio.run(run())
    assert cb.state == "open"


def test_circuit_reset():
    cb = CircuitBreaker(name="t4", failure_threshold=1, recovery_time_s=10.0)

    async def run():
        with pytest.raises(RuntimeError):
            await cb.acall(_raise)
        cb.reset()
        result = await cb.acall(_ok)
        assert result == 42

    asyncio.run(run())
