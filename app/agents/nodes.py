from __future__ import annotations

from typing import Any, Dict, List

from app.retrieval.query_router import hybrid_retrieve
from app.state import GraphState


async def retrieve_context_node(state: GraphState) -> Dict[str, Any]:
    context = await hybrid_retrieve(state["user_query"])
    return {"retrieved_context": context, "next_node": "finance_analyst"}


async def finance_analyst_node(state: GraphState) -> Dict[str, Any]:
    raw = state.get("retrieved_context", {}).get("raw", {})
    debt_ratio = raw.get("debt_ratio", 0)
    insight = "부채비율 안정" if debt_ratio < 150 else "부채비율 상승으로 재무 리스크 존재"
    payload = {"debt_ratio": debt_ratio, "insight": insight}
    return {
        "finance_metrics": payload,
        "messages": [{"role": "finance_analyst", "content": str(payload)}],
        "next_node": "risk_compliance",
    }


async def risk_compliance_node(state: GraphState) -> Dict[str, Any]:
    disclosures: List[Dict[str, Any]] = state.get("retrieved_context", {}).get("raw", {}).get("disclosures", [])
    risks = [f"{d.get('event_type')}: {d.get('summary')}" for d in disclosures] or ["중대 공시 리스크 미탐지"]
    return {
        "risk_points": risks,
        "messages": [{"role": "risk_compliance", "content": "; ".join(risks)}],
        "next_node": "orchestrator",
    }


async def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    turn = state.get("turn_count", 0) + 1
    has_fin = bool(state.get("finance_metrics"))
    has_risk = bool(state.get("risk_points"))
    consensus = has_fin and has_risk
    decision = "합의 완료" if consensus else "정보 부족"
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
    }
    return {"messages": [{"role": "final", "content": str(summary)}]}
