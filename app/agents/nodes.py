from __future__ import annotations

from typing import Any, Dict

from app.agents.llm_structured import extract_finance_metrics, extract_risk_points
from app.retrieval.query_router import hybrid_retrieve
from app.state import GraphState


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


async def retrieve_context_node(state: GraphState) -> Dict[str, Any]:
    company = state.get("target_company")
    year = state.get("target_year")
    context = await hybrid_retrieve(state["user_query"], company=company, year=year)

    return {"retrieved_context": context, "next_node": "finance_analyst"}


async def finance_analyst_node(state: GraphState) -> Dict[str, Any]:
    context = state.get("retrieved_context", {})
    payload = await extract_finance_metrics(context)
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
        "next_node": "orchestrator",
    }


# nodes.py 내의 오케스트레이터 노드 수정

async def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    turn = state.get("turn_count", 0) + 1

    has_fin = bool(state.get("finance_metrics"))
    has_risk = bool(state.get("risk_points"))
    consensus = has_fin and has_risk
    decision = _build_orchestrator_decision(state) if consensus else "재무 또는 리스크 정보가 충분하지 않아 추가 확인이 필요합니다."

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
        "system_notice": "최대 턴 수 초과로 인한 오케스트레이터의 강제 개입 및 종료" if not state.get("consensus_reached") else "정상 합의"
    }
    return {"messages": [{"role": "final", "content": str(summary)}]}