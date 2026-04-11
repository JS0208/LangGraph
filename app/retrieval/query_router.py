from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

SEED = Path("tests/seed_data/mock_dart_response.json")


def _load_seed() -> Dict[str, Any]:
    if not SEED.exists():
        return {"companies": []}
    return json.loads(SEED.read_text(encoding="utf-8"))


async def hybrid_retrieve(user_query: str) -> Dict[str, Any]:
    """Fallback-first retrieval: always returns a stable, parseable context."""
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
