from __future__ import annotations

import os

from app.state import GraphState


MAX_TURNS = int(os.getenv("MAX_TURNS", "3"))


def router_logic(state: GraphState) -> str:
    if state.get("turn_count", 0) >= MAX_TURNS:
        return "generate_final_report"

    next_node = state.get("next_node", "orchestrator")
    if next_node in {"finance_analyst", "risk_compliance", "orchestrator", "generate_final_report"}:
        return next_node
    return "orchestrator"
