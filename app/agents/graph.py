from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from typing import Any

from app.agents.edges import router_logic
from app.agents.nodes import (
    finance_analyst_node,
    generate_final_report_node,
    orchestrator_node,
    retrieve_context_node,
    risk_compliance_node,
)
from app.state import GraphState


class LocalFallbackGraph:
    """LangGraph 미설치 환경에서도 동작하는 최소 실행기."""

    async def astream(
        self,
        state: GraphState,
        config: dict[str, Any] | None = None,
        stream_mode: str = "updates",
    ) -> AsyncIterator[dict[str, Any]]:
        del config, stream_mode
        current = dict(state)
        node_map = {
            "retrieve_context": retrieve_context_node,
            "finance_analyst": finance_analyst_node,
            "risk_compliance": risk_compliance_node,
            "orchestrator": orchestrator_node,
            "generate_final_report": generate_final_report_node,
        }
        next_node = "retrieve_context"
        while True:
            fn = node_map[next_node]
            update = await fn(current)
            current.update(update)
            yield {next_node: update}
            if next_node == "generate_final_report":
                break
            next_node = router_logic(current)  # type: ignore[arg-type]


def _build_with_langgraph():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(GraphState)
    graph.add_node("retrieve_context", retrieve_context_node)
    graph.add_node("finance_analyst", finance_analyst_node)
    graph.add_node("risk_compliance", risk_compliance_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("generate_final_report", generate_final_report_node)

    graph.add_edge(START, "retrieve_context")
    graph.add_conditional_edges("retrieve_context", router_logic)
    graph.add_conditional_edges("finance_analyst", router_logic)
    graph.add_conditional_edges("risk_compliance", router_logic)
    graph.add_conditional_edges("orchestrator", router_logic)
    graph.add_edge("generate_final_report", END)

    return graph.compile(checkpointer=MemorySaver())


def build_graph():
    if importlib.util.find_spec("langgraph") is None:
        return LocalFallbackGraph()
    return _build_with_langgraph()
