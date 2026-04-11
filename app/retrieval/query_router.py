from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.config import settings
from app.retrieval.real_clients import extract_company_year, neo4j_two_hop, qdrant_search

SEED = Path("tests/seed_data/mock_dart_response.json")


def _load_seed() -> Dict[str, Any]:
    if not SEED.exists():
        return {"companies": []}
    return json.loads(SEED.read_text(encoding="utf-8"))


async def hybrid_retrieve(user_query: str) -> Dict[str, Any]:
    """Fallback-first retrieval: always returns a stable, parseable context."""
    company, year = extract_company_year(user_query)
    if settings.has_real_retrieval:
        try:
            vector = await qdrant_search(
                qdrant_url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                collection=settings.qdrant_collection,
                user_query=user_query,
                company=company,
                year=year,
                limit=5,
            )
            graph = await neo4j_two_hop(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
                company=company,
            )
            return {
                "query": user_query,
                "vector_results": vector,
                "graph_results": graph,
                "raw": {"name": company or "UNKNOWN", "year": year or 0},
                "mode": "real",
            }
        except Exception:
            # 실연동 실패 시 즉시 seed fallback
            pass

    seed = _load_seed()
    companies = seed.get("companies", [])
    target = companies[0] if companies else {}
    return {
        "query": user_query,
        "vector_results": [
            {
                "chunk_id": "seed-001",
                "source_type": "DART_REPORT",
                "company_name": target.get("name", "UNKNOWN"),
                "year": target.get("year", 2024),
                "text_content": f"{target.get('name', '기업')} 재무/공시 요약",
            }
        ],
        "graph_results": {
            "nodes": [target.get("name", "Company")],
            "edges": ["HAS_REPORT", "INVOLVED_IN"],
        },
        "raw": target,
    }
