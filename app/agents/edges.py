from __future__ import annotations

import os

from app.state import GraphState


MAX_TURNS = int(os.getenv("MAX_TURNS", "3"))
MAX_REFLEXIONS = int(os.getenv("MAX_REFLEXIONS", "2"))

VALID_NODES = {
    "intent_classifier",
    "retrieve_context",
    "finance_analyst",
    "risk_compliance",
    "critic",
    "reflector",
    "orchestrator",
    "generate_final_report",
}


def router_logic(state: GraphState) -> str:
    if state.get("turn_count", 0) >= MAX_TURNS:
        return "generate_final_report"

    next_node = state.get("next_node", "orchestrator")
    if next_node in VALID_NODES:
        return next_node
    return "orchestrator"
