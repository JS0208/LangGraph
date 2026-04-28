from __future__ import annotations

import logging
from typing import Any, Dict

from app.agents.llm_structured import extract_finance_metrics, extract_risk_points
from app.retrieval.query_planner import plan_query
from app.retrieval.query_router import hybrid_retrieve
from app.schemas import QueryPlan
from app.state import GraphState, STATE_SCHEMA_VERSION

logger = logging.getLogger(__name__)


def _evidence_ids(retrieved_context: Dict[str, Any]) -> list[str]:
    return [str(ev.get("evidence_id", "")) for ev in retrieved_context.get("evidence", []) if ev.get("evidence_id")]


def _build_orchestrator_decision(state: GraphState) -> str:
    finance_metrics = state.get("finance_metrics", {})
    finance_insight = str(finance_metrics.get("insight", "")).strip()
    risk_points = [str(point).strip() for point in state.get("risk_points", []) if str(point).strip()]
    analysis_context = state.get("retrieved_context", {}).get("analysis_context", {})
    data_quality = analysis_context.get("data_quality", {})
    flags = [str(flag) for flag in data_quality.get("flags", []) if str(flag)]
    mode = data_quality.get("mode", state.get("retrieved_context", {}).get("mode", "fallback"))

    summary_parts: list[str] = []
    if finance_insight:
        summary_parts.append(finance_insight)
    if risk_points and risk_points != ["중대 공시 리스크 미탐지"]:
        summary_parts.append(f"주요 리스크는 {', '.join(risk_points[:2])}입니다.")

    if flags:
        summary_parts.append(
            f"다만 데이터 품질 제약({', '.join(flags[:3])}) 때문에 결론은 보수적으로 해석해야 합니다."
        )
    elif mode in {"partial_real", "fallback"}:
        summary_parts.append(f"현재 응답은 `{mode}` 모드 기반이므로 추가 확인이 필요합니다.")

    return " ".join(summary_parts) or "재무 및 공시 정보가 충분하지 않아 추가 확인이 필요합니다."


# --- Sprint 3 신규 노드 ----------------------------------------------------


async def intent_classifier_node(state: GraphState) -> Dict[str, Any]:
    """Sprint 3: Query 의 in/out scope + 의도를 결정. plan_query 의 의도 라벨을 그대로 사용."""
    plan = await plan_query(state["user_query"])
    next_node = "retrieve_context" if plan.overall_intent != "out_of_scope" else "generate_final_report"
    return {
        "intent": plan.overall_intent,
        "query_plan": plan.model_dump(),
        "schema_version": STATE_SCHEMA_VERSION,
        "next_node": next_node,
    }


# --- 기존 노드 보강 -------------------------------------------------------


async def retrieve_context_node(state: GraphState) -> Dict[str, Any]:
    company = state.get("target_company")
    year = state.get("target_year")
    plan_dict = state.get("query_plan")
    plan = QueryPlan.model_validate(plan_dict) if plan_dict else None

    context = await hybrid_retrieve(state["user_query"], company=company, year=year, plan=plan)

    return {
        "retrieved_context": context,
        "evidence": list(context.get("evidence", [])),
        "next_node": "finance_analyst",
    }


async def finance_analyst_node(state: GraphState) -> Dict[str, Any]:
    context = state.get("retrieved_context", {})
    payload = await extract_finance_metrics(context)
    payload.setdefault("evidence_ids", _evidence_ids(context))
    return {
        "finance_metrics": payload,
        "messages": [{"role": "finance_analyst", "content": str(payload)}],
        "next_node": "risk_compliance",
    }


async def risk_compliance_node(state: GraphState) -> Dict[str, Any]:
    context = state.get("retrieved_context", {})
    risks = await extract_risk_points(context)
    return {
        "risk_points": risks,
        "messages": [{"role": "risk_compliance", "content": "; ".join(risks)}],
        "next_node": "critic",
    }


async def critic_node(state: GraphState) -> Dict[str, Any]:
    """Sprint 3: 두 분석가 출력의 (a) 인용 누락, (b) 일반론, (c) 모순 을 점수화."""
    finance_metrics = state.get("finance_metrics", {}) or {}
    risk_points = state.get("risk_points", []) or []
    analysis_context = state.get("retrieved_context", {}).get("analysis_context", {})
    data_quality = analysis_context.get("data_quality", {})
    flags = list(data_quality.get("flags", []))
    has_evidence = bool(state.get("evidence"))

    missing_citations: list[str] = []
    if not finance_metrics.get("evidence_ids"):
        missing_citations.append("finance_metrics.evidence_ids")
    if not risk_points:
        missing_citations.append("risk_points")

    contradictions: list[str] = []
    debt = finance_metrics.get("debt_ratio")
    insight = str(finance_metrics.get("insight", ""))
    if isinstance(debt, (int, float)) and debt and debt < 150 and "상승" in insight:
        contradictions.append("debt_ratio < 150 인데 insight 가 상승을 단정")
    if isinstance(debt, (int, float)) and debt and debt > 200 and "안정" in insight:
        contradictions.append("debt_ratio > 200 인데 insight 가 안정을 단정")

    score = 0.0
    if missing_citations:
        score += 0.4
    if not has_evidence:
        score += 0.2
    if contradictions:
        score += 0.4
    if "financial_parse_failed" in flags or "financial_context_missing" in flags:
        score += 0.1
    if not finance_metrics.get("has_sufficient_data") and not risk_points:
        score += 0.1
    score = min(1.0, score)

    request_re_retrieval = bool(score >= 0.5 and state.get("reflexion_count", 0) < 2 and not has_evidence)

    critic_report = {
        "disagreement_score": score,
        "missing_citations": missing_citations,
        "contradictions": contradictions,
        "request_re_retrieval": request_re_retrieval,
        "notes": ", ".join(flags[:3]) if flags else "ok",
    }

    next_node = "reflector" if request_re_retrieval else "orchestrator"
    return {
        "critic_report": critic_report,
        "disagreement_score": score,
        "messages": [{"role": "critic", "content": str(critic_report)}],
        "next_node": next_node,
    }


async def reflector_node(state: GraphState) -> Dict[str, Any]:
    """Sprint 3: critic 이 재검색을 요청하면 plan 을 한 번 더 정제하여 재시도한다.

    안전: ``reflexion_count`` 가 ``MAX_REFLEXIONS`` 에 도달하면 강제로 orchestrator 로 회귀.
    """
    from app.agents.edges import MAX_REFLEXIONS

    count = state.get("reflexion_count", 0) + 1
    if count > MAX_REFLEXIONS:
        return {
            "reflexion_count": count,
            "messages": [{"role": "reflector", "content": "MAX_REFLEXIONS 도달 — orchestrator 로 강제 회귀"}],
            "next_node": "orchestrator",
        }
    # 단순 재계획: 기존 plan 의 sub_queries 가중치를 1.2x 로 부스트
    plan_dict = state.get("query_plan") or {}
    try:
        plan = QueryPlan.model_validate(plan_dict)
        boosted = []
        for sq in plan.sub_queries:
            boosted_sq = sq.model_copy(update={"weight": min(1.5, sq.weight * 1.2)})
            boosted.append(boosted_sq)
        plan = plan.model_copy(update={"sub_queries": boosted})
        new_plan = plan.model_dump()
    except Exception:
        new_plan = plan_dict

    return {
        "reflexion_count": count,
        "query_plan": new_plan,
        "messages": [{"role": "reflector", "content": "재검색 요청: 가중치 부스트 + retrieve_context 재실행"}],
        "next_node": "retrieve_context",
    }


async def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    turn = state.get("turn_count", 0) + 1
    score = float(state.get("disagreement_score", 0.0) or 0.0)

    has_fin = bool(state.get("finance_metrics"))
    has_risk = bool(state.get("risk_points"))
    consensus = has_fin and has_risk and score <= 0.2
    decision = (
        _build_orchestrator_decision(state)
        if consensus
        else f"재무 또는 리스크 정보가 충분하지 않아 추가 확인이 필요합니다. (disagreement={score:.2f})"
    )

    return {
        "turn_count": turn,
        "consensus_reached": consensus,
        "messages": [{"role": "orchestrator", "content": decision}],
        "next_node": "generate_final_report",
    }


async def generate_final_report_node(state: GraphState) -> Dict[str, Any]:
    summary = {
        "finance": state.get("finance_metrics", {}),
        "risk": state.get("risk_points", []),
        "consensus_reached": state.get("consensus_reached", False),
        "turn_count": state.get("turn_count", 0),
        "intent": state.get("intent"),
        "evidence_count": len(state.get("evidence", []) or []),
        "disagreement_score": state.get("disagreement_score"),
        "system_notice": (
            "범위 외 질의로 분석 미수행"
            if state.get("intent") == "out_of_scope"
            else (
                "최대 턴 수 초과로 인한 오케스트레이터의 강제 개입 및 종료"
                if not state.get("consensus_reached")
                else "정상 합의"
            )
        ),
    }
    return {"messages": [{"role": "final", "content": str(summary)}]}
