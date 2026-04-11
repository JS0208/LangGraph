from __future__ import annotations

import asyncio

from app.agents.edges import router_logic
from app.agents.nodes import finance_analyst_node, orchestrator_node, risk_compliance_node


def test_finance_node_high_debt_risk():
    state = {
        "retrieved_context": {"raw": {"debt_ratio": 200}},
        "messages": [],
    }
    update = asyncio.run(finance_analyst_node(state))  # type: ignore[arg-type]
    assert update["finance_metrics"]["debt_ratio"] == 200
    assert "재무 리스크" in update["finance_metrics"]["insight"]


def test_risk_node_disclosures_to_points():
    state = {
        "retrieved_context": {
            "raw": {
                "disclosures": [
                    {"event_type": "REGULATION", "summary": "규제 조사"},
                    {"event_type": "M&A", "summary": "인수 검토"},
                ]
            }
        }
    }
    update = asyncio.run(risk_compliance_node(state))  # type: ignore[arg-type]
    assert len(update["risk_points"]) == 2


def test_orchestrator_increments_turn_and_consensus():
    state = {"turn_count": 0, "finance_metrics": {"ok": True}, "risk_points": ["r1"]}
    update = asyncio.run(orchestrator_node(state))  # type: ignore[arg-type]
    assert update["turn_count"] == 1
    assert update["consensus_reached"] is True


def test_router_forces_final_when_max_turns_hit():
    state = {"turn_count": 3, "next_node": "finance_analyst"}
    assert router_logic(state) == "generate_final_report"  # type: ignore[arg-type]
