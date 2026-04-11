from __future__ import annotations

import asyncio

from app.agents.graph import LocalFallbackGraph, build_graph
from app.retrieval.query_router import hybrid_retrieve
from app.retrieval.real_clients import extract_company_year


def test_hybrid_retrieve_has_stable_shape():
    result = asyncio.run(hybrid_retrieve("카카오 리스크"))
    assert "vector_results" in result
    assert "graph_results" in result
    assert "raw" in result


def test_fallback_graph_astream_runs_end_to_end():
    graph = LocalFallbackGraph()
    init_state = {
        "user_query": "카카오 리스크",
        "messages": [],
        "turn_count": 0,
        "retrieved_context": {},
        "finance_metrics": {},
        "risk_points": [],
        "consensus_reached": False,
        "next_node": "retrieve_context",
    }

    async def run():
        updates = []
        async for item in graph.astream(init_state):
            updates.append(item)
        return updates

    updates = asyncio.run(run())
    assert updates
    assert "generate_final_report" in updates[-1]


def test_build_graph_returns_graph_like_object():
    graph = build_graph()
    assert hasattr(graph, "astream")


def test_extract_company_year_from_query():
    company, year = extract_company_year("카카오 2024년 리스크 알려줘")
    assert company == "카카오"
    assert year == 2024
