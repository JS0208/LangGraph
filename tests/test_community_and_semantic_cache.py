"""Sprint 7 — community 검출 + semantic answer cache 단위 테스트."""

from __future__ import annotations

import asyncio

import pytest

from app.retrieval.community import detect_communities, heuristic_summarize
from app.retrieval.semantic_cache import SemanticAnswerCache


def test_detect_communities_groups_connected_nodes():
    nodes = ["카카오", "카카오게임즈", "삼성전자", "삼성SDS", "외톨이"]
    edges = [("카카오", "카카오게임즈"), ("삼성전자", "삼성SDS")]
    comms = detect_communities(nodes, edges)
    # 3개 community: {카카오, 카카오게임즈}, {삼성전자, 삼성SDS}, {외톨이}
    assert len(comms) == 3
    sizes = sorted([len(c.members) for c in comms])
    assert sizes == [1, 2, 2]


def test_heuristic_summarize_emits_keywords_and_summary():
    comm = detect_communities(["삼성전자", "삼성SDS"], [("삼성전자", "삼성SDS")])[0]
    texts = [
        "삼성전자 2024년 매출 280조원, 영업이익 30조원",
        "삼성SDS 2024년 영업이익 9000억원",
    ]
    out = heuristic_summarize(comm, texts)
    assert out.summary
    assert isinstance(out.keywords, list) and out.keywords


def test_semantic_cache_exact_lookup():
    cache = SemanticAnswerCache(threshold=0.97)

    async def _go():
        await cache.store("삼성전자 2024 매출?", {"answer": "280조"})
        return await cache.lookup("삼성전자 2024 매출?")

    hit = asyncio.get_event_loop().run_until_complete(_go()) if not asyncio.get_event_loop().is_running() else None
    if hit is None:
        # alternative: pytest-asyncio 가 없을 때 직접 실행
        loop = asyncio.new_event_loop()
        try:
            hit = loop.run_until_complete(_go())
        finally:
            loop.close()
    assert hit and hit["answer"] == "280조"


def test_semantic_cache_jaccard_fallback():
    cache = SemanticAnswerCache(threshold=0.95)

    async def _go():
        await cache.store("삼성전자 2024년 매출액", {"answer": "280조"})
        # 거의 동일한 질의 — Jaccard fallback 으로 hit
        return await cache.lookup("삼성전자 2024년 매출액?")

    loop = asyncio.new_event_loop()
    try:
        hit = loop.run_until_complete(_go())
    finally:
        loop.close()
    assert hit and hit["answer"] == "280조"
