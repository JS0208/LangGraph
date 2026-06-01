"""Multi-entity parallel retrieval coordinator.

For queries mentioning 2+ companies, runs per-company searches concurrently
via asyncio.gather and merges results with deduplication.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from app.retrieval.real_clients import COMPANY_ALIAS_MAP, _normalize_company_text


_YEAR_RE = re.compile(r"(19|20)\d{2}")

_COMPARISON_KEYWORDS = (
    "비교", "대비", "vs", "versus", "차이", "compared", "compare",
    "어느 쪽", "어디가", "누가", "더 높", "더 낮", "보다",
)


def is_comparison_query(query: str) -> bool:
    """Return True if query implies multi-entity comparison."""
    lowered = query.lower()
    return any(kw in lowered for kw in _COMPARISON_KEYWORDS)


def extract_year_near_company(query: str, company: str) -> int | None:
    """Extract the year that appears closest to a company mention in query text.

    All position lookups are done on the same lowered string to ensure
    character indices are directly comparable.
    """
    lowered = query.lower()

    # Find aliases for this company
    aliases = [alias for alias, canonical in COMPANY_ALIAS_MAP.items() if canonical == company]
    if not aliases:
        aliases = []

    # Find character positions of company mention in the lowered original string
    company_pos: list[int] = []
    for alias in aliases:
        alias_lower = alias.lower()
        idx = lowered.find(alias_lower)
        if idx >= 0:
            company_pos.append(idx)

    if not company_pos:
        # Try canonical name directly
        idx = lowered.find(company.lower())
        if idx >= 0:
            company_pos.append(idx)

    if not company_pos:
        return None

    # Find all year positions in the same lowered string
    year_positions: list[tuple[int, int]] = []
    for m in _YEAR_RE.finditer(lowered):
        year_positions.append((m.start(), int(m.group())))

    if not year_positions:
        return None

    # Return the year whose start position is closest to any company mention end
    best_year = None
    best_dist = float("inf")
    for cpos in company_pos:
        for ypos, year in year_positions:
            dist = abs(ypos - cpos)
            if dist < best_dist:
                best_dist = dist
                best_year = year

    return best_year


def extract_per_company_years(query: str, companies: list[str]) -> dict[str, int | None]:
    """Return a mapping of company -> year extracted near that company's mention."""
    result: dict[str, int | None] = {}
    for company in companies:
        result[company] = extract_year_near_company(query, company)

    # If all years are None, try global year extraction
    if not any(result.values()):
        from app.retrieval.real_clients import extract_company_year
        _, global_year = extract_company_year(query)
        if global_year:
            for company in companies:
                result[company] = global_year

    return result


async def parallel_qdrant_search(
    user_query: str,
    companies: list[str],
    year_map: dict[str, int | None],
    *,
    qdrant_url: str,
    api_key: str,
    collection: str,
    limit_per_company: int = 5,
) -> list[dict[str, Any]]:
    """Run qdrant_search concurrently for each company and merge results."""
    from app.retrieval.real_clients import qdrant_search

    async def _search_one(company: str) -> list[dict[str, Any]]:
        try:
            return await qdrant_search(
                qdrant_url=qdrant_url,
                api_key=api_key,
                collection=collection,
                user_query=user_query,
                company=company,
                year=year_map.get(company),
                limit=limit_per_company,
            )
        except Exception:
            return []

    results_nested = await asyncio.gather(*[_search_one(c) for c in companies])

    # Merge and deduplicate by chunk_id
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []
    for results in results_nested:
        for item in results:
            cid = item.get("chunk_id", "")
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            merged.append(item)
    return merged


async def parallel_neo4j_hop(
    companies: list[str],
    *,
    uri: str,
    user: str,
    password: str,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Run neo4j adaptive hop for each company concurrently and merge graph results."""
    from app.retrieval.real_clients import neo4j_adaptive_hop

    async def _hop_one(company: str) -> dict[str, Any]:
        try:
            return await neo4j_adaptive_hop(
                uri=uri, user=user, password=password,
                company=company, max_depth=max_depth, min_nodes=3,
            )
        except Exception:
            return {"nodes": [company], "edges": []}

    results = await asyncio.gather(*[_hop_one(c) for c in companies])

    all_nodes: list[str] = []
    all_edges: list[str] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()
    for r in results:
        for n in r.get("nodes", []):
            if n and n not in seen_nodes:
                seen_nodes.add(n)
                all_nodes.append(n)
        for e in r.get("edges", []):
            if e and e not in seen_edges:
                seen_edges.add(e)
                all_edges.append(e)

    return {"nodes": all_nodes, "edges": all_edges}


__all__ = [
    "is_comparison_query",
    "extract_per_company_years",
    "parallel_qdrant_search",
    "parallel_neo4j_hop",
]
