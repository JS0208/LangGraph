from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from typing import Any

from app.agents.edges import MAX_REFLEXIONS, MAX_TURNS, router_logic
from app.agents.nodes import (
    critic_node,
    finance_analyst_node,
    generate_final_report_node,
    intent_classifier_node,
    orchestrator_node,
    reflector_node,
    retrieve_context_node,
    risk_compliance_node,
)
from app.state import GraphState


NODE_MAP = {
    "intent_classifier": intent_classifier_node,
    "retrieve_context": retrieve_context_node,
    "finance_analyst": finance_analyst_node,
    "risk_compliance": risk_compliance_node,
    "critic": critic_node,
    "reflector": reflector_node,
    "orchestrator": orchestrator_node,
    "generate_final_report": generate_final_report_node,
}


class LocalFallbackGraph:
    """LangGraph 미설치 환경에서도 동작하는 최소 실행기. Sprint 3 에서 critic/reflector 노드 추가."""

    async def astream(
        self,
        state: GraphState,
        config: dict[str, Any] | None = None,
        stream_mode: str = "updates",
    ) -> AsyncIterator[dict[str, Any]]:
        del config, stream_mode
        current = dict(state)
        # 안전 가드: intent 가 미리 분류되어 있으면 intent_classifier 를 건너뛴다.
        if current.get("intent") and current.get("next_node") in {None, "intent_classifier"}:
            current["next_node"] = "retrieve_context"

        next_node = current.get("next_node") or "intent_classifier"
        if next_node not in NODE_MAP:
            next_node = "intent_classifier"

        steps = 0
        # 안전 가드: 무한 루프 차단. 최악의 경우라도 (turns + reflexions + 5) 이내 종료.
        max_steps = max(8, (MAX_TURNS + MAX_REFLEXIONS) * 4)

        while True:
            steps += 1
            fn = NODE_MAP[next_node]
            update = await fn(current)
            current.update(update)
            yield {next_node: update}
            if next_node == "generate_final_report":
                break
            if steps >= max_steps:
                # 강제 종료 (이론상 도달 불가)
                terminal = await generate_final_report_node(current)
                current.update(terminal)
                yield {"generate_final_report": terminal}
                break
            next_node = router_logic(current)  # type: ignore[arg-type]
            if next_node not in NODE_MAP:
                next_node = "orchestrator"


def _build_with_langgraph():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from app.memory.saver_factory import get_checkpointer

    graph = StateGraph(GraphState)
    for name, fn in NODE_MAP.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "intent_classifier")
    graph.add_conditional_edges("intent_classifier", router_logic)
    graph.add_conditional_edges("retrieve_context", router_logic)
    graph.add_conditional_edges("finance_analyst", router_logic)
    graph.add_conditional_edges("risk_compliance", router_logic)
    graph.add_conditional_edges("critic", router_logic)
    graph.add_conditional_edges("reflector", router_logic)
    graph.add_conditional_edges("orchestrator", router_logic)
    graph.add_edge("generate_final_report", END)

    # Postgres/SQLite saver 가용 시 사용, 미가용 시 MemorySaver fallback.
    checkpointer = get_checkpointer() or MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def build_graph():
    if importlib.util.find_spec("langgraph") is None:
        return LocalFallbackGraph()
    return _build_with_langgraph()
