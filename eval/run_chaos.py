"""Chaos 6종 시나리오 평가 — Sprint 7.

monkeypatch 로 실 클라이언트를 의도적으로 깨고,
``hybrid_retrieve`` / ``LocalFallbackGraph`` 가 sane fallback 결과를 내는지 검증한다.

전제: env 는 fallback 모드. 실 자격증명을 채우면 일부 시나리오는 partial_real 로 통과한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _force_fallback() -> None:
    for key in (
        "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
        "QDRANT_URL", "QDRANT_API_KEY",
        "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
    ):
        os.environ[key] = ""


_force_fallback()


from app.agents.graph import LocalFallbackGraph  # noqa: E402
from app.retrieval import query_router  # noqa: E402
from app.retrieval.cache import InMemoryCache, set_default_cache  # noqa: E402
from app.utils.circuit import CircuitBreaker  # noqa: E402


async def _run_one(scenario: dict[str, Any]) -> dict[str, Any]:
    """한 시나리오를 실행하고 fallback 응답이 나오는지 측정."""
    set_default_cache(InMemoryCache())
    sid = scenario["id"]
    target = scenario["target"]
    fault = scenario["fault"]

    # 시나리오 별 fault 주입
    original_qdrant = query_router.qdrant_search
    original_neo4j = query_router.neo4j_two_hop
    original_qdrant_breaker = query_router.QDRANT_BREAKER
    original_neo4j_breaker = query_router.NEO4J_BREAKER

    breaker_target = CircuitBreaker(name=f"chaos-{sid}", failure_threshold=3, recovery_time_s=15.0)
    if target == "qdrant":
        query_router.QDRANT_BREAKER = breaker_target

    async def boom_qdrant(*_a: Any, **_kw: Any):
        raise RuntimeError(scenario.get("exception_message", "qdrant fault"))

    async def boom_neo4j(*_a: Any, **_kw: Any):
        raise RuntimeError(scenario.get("exception_message", "neo4j fault"))

    async def slow_qdrant(*_a: Any, **_kw: Any):
        await asyncio.sleep(min(scenario.get("delay_s", 1.0), 0.05))  # 테스트는 짧게
        raise asyncio.TimeoutError("qdrant slow")

    if fault in {"exception", "repeat_exception", "timeout"} and target == "qdrant":
        query_router.qdrant_search = slow_qdrant if fault == "timeout" else boom_qdrant
    if fault in {"exception"} and target == "neo4j":
        query_router.neo4j_two_hop = boom_neo4j

    # 실행
    breaker_open_observed = False
    if fault == "repeat_exception" and target == "qdrant":
        # 회로 차단기가 open 으로 전이되는지 직접 검증
        repeat = int(scenario.get("repeat", 5))
        for _ in range(repeat):
            try:
                await query_router.QDRANT_BREAKER.acall(
                    boom_qdrant,
                    qdrant_url="x", api_key="x", collection="x",
                    user_query="t", company=None, year=None, limit=1,
                )
            except Exception:
                pass
        breaker_open_observed = query_router.QDRANT_BREAKER.state in {"open", "half_open"}

    # Graph 실행
    graph = LocalFallbackGraph()
    init = {
        "user_query": "삼성전자 2024년 부채비율은?",
        "messages": [],
        "turn_count": 0,
        "retrieved_context": {},
        "finance_metrics": {},
        "risk_points": [],
        "consensus_reached": False,
        "next_node": "intent_classifier",
        "evidence": [],
        "reflexion_count": 0,
    }
    final_state: dict[str, Any] = {}
    try:
        async for upd in graph.astream(init):  # type: ignore[arg-type]
            for _node, payload in upd.items():
                if isinstance(payload, dict):
                    final_state.update(payload)
    finally:
        query_router.qdrant_search = original_qdrant
        query_router.neo4j_two_hop = original_neo4j
        query_router.QDRANT_BREAKER = original_qdrant_breaker
        query_router.NEO4J_BREAKER = original_neo4j_breaker

    mode = (final_state.get("retrieved_context") or {}).get("mode")
    fin_source = (final_state.get("finance_metrics") or {}).get("source")
    expected_modes = scenario.get("expected_mode_in") or []
    expected_finance_sources = scenario.get("expected_finance_source_in") or []
    expected_breaker_open = scenario.get("expected_breaker_open", False)

    passed = True
    reasons: list[str] = []
    if expected_modes and mode not in expected_modes:
        passed = False
        reasons.append(f"mode={mode} not in {expected_modes}")
    if expected_finance_sources and fin_source not in expected_finance_sources:
        passed = False
        reasons.append(f"finance.source={fin_source} not in {expected_finance_sources}")
    if expected_breaker_open and not breaker_open_observed:
        passed = False
        reasons.append("circuit breaker did not open")

    return {
        "id": sid,
        "passed": passed,
        "mode": mode,
        "finance_source": fin_source,
        "breaker_open": breaker_open_observed,
        "reasons": reasons,
    }


async def run_all(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for sc in data["scenarios"]:
        results.append(await _run_one(sc))
    pass_count = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "pass_rate": pass_count / len(results) if results else 0.0,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(ROOT / "eval" / "chaos" / "v0.json"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.83)
    args = parser.parse_args()

    result = asyncio.run(run_all(Path(args.path)))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("# Chaos Eval (v0)")
        print(f"- total: {result['total']}")
        print(f"- pass_rate: {result['pass_rate']:.2%}")
        for c in result["cases"]:
            mark = "PASS" if c["passed"] else "FAIL"
            print(
                f"  [{mark}] {c['id']} mode={c['mode']} fin={c['finance_source']} breaker_open={c['breaker_open']}"
            )
            for r in c["reasons"]:
                print(f"      - {r}")
    return 0 if result["pass_rate"] >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
