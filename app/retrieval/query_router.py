from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.config import settings
from app.retrieval.real_clients import extract_company_year, neo4j_two_hop, qdrant_search

SEED = Path(__file__).resolve().parents[2] / "tests" / "seed_data" / "mock_dart_response.json"


def _load_seed() -> Dict[str, Any]:
    if not SEED.exists():
        return {"companies": []}
    return json.loads(SEED.read_text(encoding="utf-8"))


def _build_analysis_context(
    *,
    company: str | None,
    year: int | None,
    vector_results: list[dict[str, Any]],
    graph_results: dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    financial_item = next(
        (item for item in vector_results if item.get("source_type") == "FINANCIAL_REPORT"),
        None,
    )
    disclosure_items = [item for item in vector_results if item.get("source_type") == "DISCLOSURE"]

    data_quality_flags: list[str] = []
    if financial_item:
        for flag in financial_item.get("data_quality_flags", []):
            if flag not in data_quality_flags:
                data_quality_flags.append(str(flag))
    for item in disclosure_items:
        for flag in item.get("data_quality_flags", []):
            if flag not in data_quality_flags:
                data_quality_flags.append(str(flag))

    if not financial_item:
        data_quality_flags.append("financial_context_missing")
    if not disclosure_items:
        data_quality_flags.append("disclosure_context_missing")

    financial_facts = {
        "company_name": company or (financial_item or {}).get("company_name", "UNKNOWN"),
        "year": year or (financial_item or {}).get("year", 0),
        "quarter": (financial_item or {}).get("quarter"),
        "revenue": (financial_item or {}).get("revenue"),
        "operating_profit": (financial_item or {}).get("operating_profit"),
        "debt_ratio": (financial_item or {}).get("debt_ratio"),
        "has_financial_data": (financial_item or {}).get("has_financial_data", False),
    }
    key_disclosures = [
        {
            "date": item.get("date"),
            "event_type": item.get("event_type"),
            "summary": item.get("summary") or item.get("text_content", ""),
        }
        for item in disclosure_items[:5]
    ]

    return {
        "financial_facts": financial_facts,
        "key_disclosures": key_disclosures,
        "graph_signals": {
            "nodes": graph_results.get("nodes", []),
            "edges": graph_results.get("edges", []),
        },
        "data_quality": {
            "mode": mode,
            "flags": data_quality_flags,
            "has_financial_data": bool(financial_facts.get("has_financial_data")),
            "has_disclosures": bool(key_disclosures),
        },
    }


async def hybrid_retrieve(
    user_query: str,
    *,
    company: str | None = None,
    year: int | None = None,
) -> Dict[str, Any]:
    """Fallback-first retrieval: always returns a stable, parseable context."""
    if company is None or year is None:
        parsed_company, parsed_year = extract_company_year(user_query)
        company = company or parsed_company
        year = year or parsed_year

    if settings.has_real_retrieval:
        vector_results: list[dict[str, Any]] = []
        graph_results: dict[str, Any] = {"nodes": [], "edges": []}

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
            vector_results = vector
        except Exception:
            pass

        try:
            graph = await neo4j_two_hop(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password,
                company=company,
            )
            graph_results = graph
        except Exception:
            pass

        if vector_results or graph_results.get("nodes") or graph_results.get("edges"):
            mode = "real"
            if not vector_results or not (graph_results.get("nodes") or graph_results.get("edges")):
                mode = "partial_real"
            analysis_context = _build_analysis_context(
                company=company,
                year=year,
                vector_results=vector_results,
                graph_results=graph_results,
                mode=mode,
            )
            return {
                "query": user_query,
                "vector_results": vector_results,
                "graph_results": graph_results,
                "raw": {
                    "name": company or "UNKNOWN",
                    "year": year or 0,
                    "financial_facts": analysis_context["financial_facts"],
                    "disclosures": analysis_context["key_disclosures"],
                    "data_quality": analysis_context["data_quality"],
                },
                "analysis_context": analysis_context,
                "mode": mode,
            }

    seed = _load_seed()
    companies = seed.get("companies", [])
    target = companies[0] if companies else {}
    analysis_context = {
        "financial_facts": {
            "company_name": target.get("name", "UNKNOWN"),
            "year": target.get("year", 2024),
            "quarter": target.get("quarter"),
            "revenue": target.get("revenue"),
            "operating_profit": target.get("operating_profit"),
            "debt_ratio": target.get("debt_ratio"),
            "has_financial_data": True,
        },
        "key_disclosures": target.get("disclosures", []),
        "graph_signals": {
            "nodes": [target.get("name", "Company")],
            "edges": ["HAS_REPORT", "INVOLVED_IN"],
        },
        "data_quality": {
            "mode": "fallback",
            "flags": ["seed_fallback"],
            "has_financial_data": True,
            "has_disclosures": bool(target.get("disclosures")),
        },
    }
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
        "raw": {
            **target,
            "financial_facts": analysis_context["financial_facts"],
            "data_quality": analysis_context["data_quality"],
        },
        "analysis_context": analysis_context,
        "mode": "fallback",
    }
