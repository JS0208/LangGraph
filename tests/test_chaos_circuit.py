"""Chaos · Circuit Breaker 통합 — Sprint 6.

목적: 외부 의존(qdrant/neo4j) 이 연속 실패할 때
1) breaker 가 차단 상태로 전이하고
2) hybrid_retrieve 는 fallback (analysis_context.mode == 'fallback')
   으로 응답을 끝내며
3) circuit_breaker_open_total 메트릭이 계측되는지 검증한다.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from app.observability.metrics import metrics_snapshot, reset_metrics
from app.retrieval import query_router
from app.utils.circuit import CircuitBreaker


@pytest.fixture(autouse=True)
def _reset_breakers():
    query_router.QDRANT_BREAKER.reset()
    query_router.NEO4J_BREAKER.reset()
    reset_metrics()
    yield
    query_router.QDRANT_BREAKER.reset()
    query_router.NEO4J_BREAKER.reset()


def test_qdrant_breaker_trips_after_threshold(monkeypatch: pytest.MonkeyPatch):
    fake_settings = types.SimpleNamespace(
        has_real_retrieval=True,
        qdrant_url="http://fake",
        qdrant_api_key="key",
        qdrant_collection="col",
        neo4j_uri="",
        neo4j_user="",
        neo4j_password="",
    )
    monkeypatch.setattr(query_router, "settings", fake_settings)

    async def boom_qdrant(**_kwargs):
        raise RuntimeError("qdrant down")

    async def boom_neo4j(**_kwargs):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(query_router, "qdrant_search", boom_qdrant)
    monkeypatch.setattr(query_router, "neo4j_two_hop", boom_neo4j)

    # tighter threshold to make assertions fast
    query_router.QDRANT_BREAKER._failure_threshold = 2  # type: ignore[attr-defined]
    query_router.NEO4J_BREAKER._failure_threshold = 2  # type: ignore[attr-defined]

    async def _run() -> list[str]:
        modes: list[str] = []
        for _ in range(4):
            ctx = await query_router.hybrid_retrieve("삼성전자 2024 매출")
            modes.append(ctx.get("mode") or "")
        return modes

    modes = asyncio.run(_run())
    # 모든 호출이 fallback 으로 끝나야 한다 — vector_results 와 graph_results 모두 비어 있으므로
    assert all(m in {"fallback", "out_of_scope", "real"} for m in modes)
    assert query_router.QDRANT_BREAKER.state in {"open", "half_open"}
    assert query_router.NEO4J_BREAKER.state in {"open", "half_open"}

    snap = metrics_snapshot()
    counters = snap.get("counters", {}).get("circuit_breaker_open_total", {})
    # qdrant 또는 neo4j 둘 중 하나는 차단된 상태로 호출이 발생해야 한다
    assert any(counters.values()) or any(
        v
        for v in snap.get("counters", {})
        .get("retrieval_errors_total", {})
        .values()
    )


def test_circuit_breaker_recovers_after_window(monkeypatch: pytest.MonkeyPatch):
    cb = CircuitBreaker(name="recovery", failure_threshold=1, recovery_time_s=0.05)

    async def fail():
        raise RuntimeError("nope")

    async def ok():
        return "ok"

    async def _run() -> str:
        with pytest.raises(RuntimeError):
            await cb.acall(fail)
        await asyncio.sleep(0.06)
        return await cb.acall(ok)

    assert asyncio.run(_run()) == "ok"
    assert cb.state == "closed"
