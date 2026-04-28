from __future__ import annotations

import asyncio

import pytest

from app.agents.edges import VALID_NODES
from app.agents.graph import LocalFallbackGraph
from app.agents.nodes import (
    critic_node,
    intent_classifier_node,
    reflector_node,
)
from app.retrieval.cache import InMemoryCache, set_default_cache


@pytest.fixture(autouse=True)
def _isolate_cache():
    set_default_cache(InMemoryCache())
    yield
    set_default_cache(None)


def test_intent_classifier_routes_in_scope_query():
    state = {"user_query": "삼성전자의 2024년 매출액"}
    update = asyncio.run(intent_classifier_node(state))  # type: ignore[arg-type]
    assert update["intent"] in {"facts", "trend", "relation", "risk"}
    assert update["next_node"] == "retrieve_context"
    assert update["query_plan"]["sub_queries"]


def test_intent_classifier_routes_out_of_scope_to_final():
    state = {"user_query": "오늘 점심으로 김치찌개 먹을까?"}
    update = asyncio.run(intent_classifier_node(state))  # type: ignore[arg-type]
    assert update["intent"] == "out_of_scope"
    assert update["next_node"] == "generate_final_report"


def test_critic_flags_missing_evidence_and_routes_to_reflector():
    state = {
        "finance_metrics": {"debt_ratio": 100, "insight": "안정", "evidence_ids": []},
        "risk_points": [],
        "evidence": [],
        "retrieved_context": {"analysis_context": {"data_quality": {"flags": []}}},
        "reflexion_count": 0,
    }
    update = asyncio.run(critic_node(state))  # type: ignore[arg-type]
    assert update["disagreement_score"] >= 0.5
    assert update["critic_report"]["request_re_retrieval"] is True
    assert update["next_node"] == "reflector"


def test_critic_flags_contradiction():
    state = {
        "finance_metrics": {"debt_ratio": 250, "insight": "재무 안정", "evidence_ids": ["qd:x"]},
        "risk_points": ["규제"],
        "evidence": [{"evidence_id": "qd:x"}],
        "retrieved_context": {"analysis_context": {"data_quality": {"flags": []}}},
        "reflexion_count": 0,
    }
    update = asyncio.run(critic_node(state))  # type: ignore[arg-type]
    assert update["critic_report"]["contradictions"]


def test_critic_with_strong_evidence_routes_to_orchestrator():
    state = {
        "finance_metrics": {"debt_ratio": 80, "insight": "부채비율 안정", "evidence_ids": ["qd:1"]},
        "risk_points": ["규제 조사 진행"],
        "evidence": [{"evidence_id": "qd:1"}],
        "retrieved_context": {"analysis_context": {"data_quality": {"flags": []}}},
        "reflexion_count": 0,
    }
    update = asyncio.run(critic_node(state))  # type: ignore[arg-type]
    assert update["disagreement_score"] <= 0.3
    assert update["next_node"] == "orchestrator"


def test_reflector_caps_at_max_reflexions():
    from app.agents.edges import MAX_REFLEXIONS

    state = {
        "reflexion_count": MAX_REFLEXIONS,
        "query_plan": {"sub_queries": [], "overall_intent": "facts", "needs_graph": True, "needs_vector": True},
    }
    update = asyncio.run(reflector_node(state))  # type: ignore[arg-type]
    assert update["next_node"] == "orchestrator"
    assert update["reflexion_count"] == MAX_REFLEXIONS + 1


def test_reflector_first_iteration_re_routes_to_retrieve():
    state = {
        "reflexion_count": 0,
        "query_plan": {
            "sub_queries": [{"text": "x", "intent": "facts", "weight": 1.0}],
            "overall_intent": "facts",
            "needs_graph": True,
            "needs_vector": True,
        },
    }
    update = asyncio.run(reflector_node(state))  # type: ignore[arg-type]
    assert update["next_node"] == "retrieve_context"
    assert update["reflexion_count"] == 1


def test_local_fallback_graph_runs_end_to_end_from_intent_classifier():
    graph = LocalFallbackGraph()
    init = {
        "user_query": "카카오의 2024년 리스크",
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

    async def run():
        out = []
        async for item in graph.astream(init):
            out.append(item)
        return out

    updates = asyncio.run(run())
    visited = [list(u.keys())[0] for u in updates]
    assert "intent_classifier" in visited
    assert "retrieve_context" in visited
    assert "critic" in visited
    assert visited[-1] == "generate_final_report"


def test_out_of_scope_short_circuits_to_final_in_local_graph():
    graph = LocalFallbackGraph()
    init = {
        "user_query": "오늘 점심 메뉴 추천",
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

    async def run():
        out = []
        async for item in graph.astream(init):
            out.append(item)
        return out

    updates = asyncio.run(run())
    visited = [list(u.keys())[0] for u in updates]
    assert visited[0] == "intent_classifier"
    assert "retrieve_context" not in visited
    assert visited[-1] == "generate_final_report"


def test_valid_nodes_set_matches_node_map():
    from app.agents.graph import NODE_MAP

    assert VALID_NODES == set(NODE_MAP.keys())
