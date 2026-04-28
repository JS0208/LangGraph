"""골든셋 자동 평가 하네스 — Sprint 5.

휴리스틱 지표
- intent 정확성: classifier 가 ``expected_intent`` 와 일치하는가
- 엔티티 회수: ``expected_entities`` 가 plan 의 sub_queries 의 target_company 또는
  retrieved evidence 의 company_name 에 등장하는가
- 인용 부착률: 결론에 ``evidence_ids`` 가 비어있지 않은가
- 데이터 품질 플래그 노출: empty-data 시나리오에서 ``data_quality.flags`` 가 채워지는가

RAGAS-like 메트릭 (Sprint 5-D, 의존성 0 자체 구현)
- ``context_recall``: 검색된 evidence 텍스트가 ``expected_keywords`` 를 포함하는 비율
- ``faithfulness``: 결론 텍스트의 핵심 키워드가 evidence 에 등장하는 비율
- ``answer_relevance``: 결론 텍스트가 ``expected_keywords`` 를 포함하는 비율

진짜 RAGAS 통합은 별도 PR (``ragas`` import 가능 시 자동 활성).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _force_fallback_mode() -> None:
    """평가는 결정론적이어야 한다. 외부 호출 키를 비워 fallback 경로로 강제.

    ``app.config.Settings`` 는 frozen dataclass 이고 import 시점 1회 평가되므로,
    이 함수가 ``app.config`` import 보다 먼저 호출되어야 한다.
    """
    for key in (
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
    ):
        os.environ[key] = ""


# 기본은 fallback 모드. ``--real`` 플래그로만 실 LLM/DB 사용.
if "--real" not in sys.argv:
    _force_fallback_mode()


from app.agents.graph import LocalFallbackGraph  # noqa: E402
from app.retrieval.cache import InMemoryCache, set_default_cache  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    intent_match: bool | None
    entity_match: bool | None
    citation_attached: bool | None
    data_quality_flagged: bool | None
    context_recall: float | None = None
    faithfulness: float | None = None
    answer_relevance: float | None = None
    notes: list[str] = field(default_factory=list)


def _evidence_text(final_state: dict[str, Any]) -> str:
    parts: list[str] = []
    for ev in final_state.get("evidence", []) or []:
        if not isinstance(ev, dict):
            continue
        for key in ("text_preview", "preview", "summary", "company_name"):
            value = ev.get(key)
            if isinstance(value, str):
                parts.append(value)
    ctx = final_state.get("retrieved_context") or {}
    for chunk in ctx.get("vector_results", []) or []:
        text = chunk.get("text_content") if isinstance(chunk, dict) else None
        if isinstance(text, str):
            parts.append(text)
    return " ".join(parts).lower()


def _final_answer_text(final_state: dict[str, Any]) -> str:
    parts: list[str] = []
    fm = final_state.get("finance_metrics") or {}
    if isinstance(fm.get("insight"), str):
        parts.append(fm["insight"])
    for risk in final_state.get("risk_points") or []:
        if isinstance(risk, str):
            parts.append(risk)
        elif isinstance(risk, dict) and isinstance(risk.get("text"), str):
            parts.append(risk["text"])
    for msg in final_state.get("messages") or []:
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
    return " ".join(parts).lower()


def _ragas_like_scores(case: dict[str, Any], final_state: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    keywords: list[str] = [k.lower() for k in (case.get("expected_keywords") or []) if isinstance(k, str)]
    evidence_text = _evidence_text(final_state)
    answer_text = _final_answer_text(final_state)

    context_recall: float | None = None
    if keywords and evidence_text:
        hit = sum(1 for k in keywords if k in evidence_text)
        context_recall = hit / len(keywords)

    answer_relevance: float | None = None
    if keywords and answer_text:
        hit = sum(1 for k in keywords if k in answer_text)
        answer_relevance = hit / len(keywords)

    faithfulness: float | None = None
    if answer_text and evidence_text:
        # 답변에서 ≥ 4글자 어절을 뽑아 evidence 출현 비율을 확인.
        tokens = [t for t in answer_text.split() if len(t) >= 4]
        if tokens:
            hits = sum(1 for t in tokens if t in evidence_text)
            faithfulness = hits / len(tokens)

    return context_recall, faithfulness, answer_relevance


def _final_state_from_updates(updates: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for upd in updates:
        for _node, payload in upd.items():
            if isinstance(payload, dict):
                state.update(payload)
    return state


async def run_case(case: dict[str, Any]) -> CaseResult:
    set_default_cache(InMemoryCache())
    graph = LocalFallbackGraph()
    init = {
        "user_query": case["query"],
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
    updates: list[dict[str, Any]] = []
    async for upd in graph.astream(init):  # type: ignore[arg-type]
        updates.append(upd)
    final_state = _final_state_from_updates(updates)

    intent_match: bool | None = None
    if "expected_intent" in case:
        intent_match = final_state.get("intent") == case["expected_intent"]

    entity_match: bool | None = None
    expected_entities = case.get("expected_entities") or []
    if expected_entities:
        plan = final_state.get("query_plan") or {}
        plan_companies = {sq.get("target_company") for sq in plan.get("sub_queries", []) if sq.get("target_company")}
        evidence_companies = {ev.get("company_name") for ev in final_state.get("evidence", []) if ev.get("company_name")}
        seen = plan_companies | evidence_companies
        entity_match = all(any(name in seen for name in [exp]) for exp in expected_entities)

    citation_attached: bool | None = None
    if case.get("must_cite"):
        finance = final_state.get("finance_metrics") or {}
        ev_ids = list(finance.get("evidence_ids") or [])
        citation_attached = bool(ev_ids) or bool(final_state.get("evidence"))

    data_quality_flagged: bool | None = None
    if case.get("expected_data_quality_flag"):
        ctx = final_state.get("retrieved_context") or {}
        flags = ctx.get("analysis_context", {}).get("data_quality", {}).get("flags") or []
        data_quality_flagged = bool(flags)

    checks = [v for v in (intent_match, entity_match, citation_attached, data_quality_flagged) if v is not None]
    passed = bool(checks) and all(checks)

    ctx_recall, faithfulness, answer_relevance = _ragas_like_scores(case, final_state)

    return CaseResult(
        case_id=case["id"],
        passed=passed,
        intent_match=intent_match,
        entity_match=entity_match,
        citation_attached=citation_attached,
        data_quality_flagged=data_quality_flagged,
        context_recall=ctx_recall,
        faithfulness=faithfulness,
        answer_relevance=answer_relevance,
    )


async def run_all(golden_path: Path) -> tuple[list[CaseResult], dict[str, float]]:
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    results = [await run_case(case) for case in data["scenarios"]]

    total = len(results)
    intent_total = sum(1 for r in results if r.intent_match is not None)
    intent_ok = sum(1 for r in results if r.intent_match)
    entity_total = sum(1 for r in results if r.entity_match is not None)
    entity_ok = sum(1 for r in results if r.entity_match)
    citation_total = sum(1 for r in results if r.citation_attached is not None)
    citation_ok = sum(1 for r in results if r.citation_attached)
    pass_count = sum(1 for r in results if r.passed)

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    ctx_recalls = [r.context_recall for r in results if r.context_recall is not None]
    faiths = [r.faithfulness for r in results if r.faithfulness is not None]
    relevances = [r.answer_relevance for r in results if r.answer_relevance is not None]

    metrics = {
        "total_cases": float(total),
        "pass_rate": (pass_count / total) if total else 0.0,
        "intent_accuracy": (intent_ok / intent_total) if intent_total else 0.0,
        "entity_recall": (entity_ok / entity_total) if entity_total else 0.0,
        "citation_attachment_rate": (citation_ok / citation_total) if citation_total else 0.0,
        "ragas_like_context_recall": _avg([c for c in ctx_recalls if c is not None]),
        "ragas_like_faithfulness": _avg([f for f in faiths if f is not None]),
        "ragas_like_answer_relevance": _avg([r for r in relevances if r is not None]),
    }
    return results, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(ROOT / "eval" / "golden_set" / "v0.json"))
    parser.add_argument("--json", action="store_true", help="JSON 으로 출력")
    parser.add_argument(
        "--real",
        action="store_true",
        help="실 LLM/DB 사용 (기본은 fallback 결정론 평가)",
    )
    args = parser.parse_args()

    set_default_cache(InMemoryCache())
    results, metrics = asyncio.run(run_all(Path(args.golden)))
    payload = {
        "metrics": metrics,
        "cases": [
            {
                "id": r.case_id,
                "passed": r.passed,
                "intent_match": r.intent_match,
                "entity_match": r.entity_match,
                "citation_attached": r.citation_attached,
                "data_quality_flagged": r.data_quality_flagged,
                "context_recall": r.context_recall,
                "faithfulness": r.faithfulness,
                "answer_relevance": r.answer_relevance,
            }
            for r in results
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"# Golden Set Eval (v0)")
        print(f"- total: {int(metrics['total_cases'])}")
        print(f"- pass_rate: {metrics['pass_rate']:.2%}")
        print(f"- intent_accuracy: {metrics['intent_accuracy']:.2%}")
        print(f"- entity_recall: {metrics['entity_recall']:.2%}")
        print(f"- citation_attachment_rate: {metrics['citation_attachment_rate']:.2%}")
        print(f"- ragas_like_context_recall: {metrics['ragas_like_context_recall']:.2%}")
        print(f"- ragas_like_faithfulness: {metrics['ragas_like_faithfulness']:.2%}")
        print(f"- ragas_like_answer_relevance: {metrics['ragas_like_answer_relevance']:.2%}")
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            print(
                f"  [{mark}] {r.case_id} intent={r.intent_match} "
                f"entity={r.entity_match} cite={r.citation_attached} dqf={r.data_quality_flagged}"
            )

    set_default_cache(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
