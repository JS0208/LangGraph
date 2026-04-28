from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable

from app.config import settings
from app.observability.metrics import counter_inc
from app.retrieval.real_clients import extract_company_year, neo4j_two_hop, qdrant_search
from app.retrieval.query_planner import plan_query
from app.schemas import Evidence, QueryPlan
from app.utils.circuit import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

QDRANT_BREAKER = CircuitBreaker(name="qdrant", failure_threshold=3, recovery_time_s=15.0)
NEO4J_BREAKER = CircuitBreaker(name="neo4j", failure_threshold=3, recovery_time_s=15.0)

SEED = Path(__file__).resolve().parents[2] / "tests" / "seed_data" / "mock_dart_response.json"


def _load_seed() -> Dict[str, Any]:
    if not SEED.exists():
        return {"companies": []}
    return json.loads(SEED.read_text(encoding="utf-8"))


def _make_evidence_id(item: dict[str, Any], idx: int) -> str:
    raw_id = item.get("chunk_id") or item.get("id")
    if raw_id:
        return f"qd:{raw_id}"
    return f"qd:idx{idx}"


def _hits_to_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """vector hits 를 Evidence(model_dump 형태)로 변환."""
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        source_type = str(item.get("source_type", "DART_REPORT"))
        if source_type not in {"FINANCIAL_REPORT", "DISCLOSURE", "DART_REPORT", "GRAPH", "NEWS", "SEED", "USER_PROVIDED"}:
            source_type = "DART_REPORT"
        text = item.get("text_content") or item.get("summary") or ""
        ev = Evidence(
            evidence_id=_make_evidence_id(item, idx),
            source_type=source_type,  # type: ignore[arg-type]
            company_name=item.get("company_name"),
            year=item.get("year") if isinstance(item.get("year"), int) else None,
            text_preview=text[:240],
            metadata={
                "retrieval_strategy": item.get("retrieval_strategy", "unknown"),
                "data_quality_flags": list(item.get("data_quality_flags", []) or []),
            },
        )
        out.append(ev.model_dump())
    return out


def _graph_to_evidence(graph_results: dict[str, Any], company: str | None) -> list[dict[str, Any]]:
    nodes = graph_results.get("nodes") or []
    if not nodes:
        return []
    name = company or (nodes[0] if nodes else "graph")
    ev = Evidence(
        evidence_id=f"graph:{name}",
        source_type="GRAPH",
        company_name=name,
        text_preview=f"linked nodes={len(nodes)}, edges={len(graph_results.get('edges') or [])}",
        metadata={"nodes": list(nodes)[:20], "edges": list(graph_results.get("edges") or [])[:20]},
    )
    return [ev.model_dump()]


def _build_analysis_context(
    *,
    company: str | None,
    year: int | None,
    vector_results: list[dict[str, Any]],
    graph_results: dict[str, Any],
    mode: str,
    plan: QueryPlan | None = None,
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

    context: Dict[str, Any] = {
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
    if plan is not None:
        context["query_plan"] = plan.model_dump()
    return context


async def _run_real_retrieval(
    user_query: str,
    *,
    company: str | None,
    year: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    vector_results: list[dict[str, Any]] = []
    graph_results: dict[str, Any] = {"nodes": [], "edges": []}

    try:
        vector_results = await QDRANT_BREAKER.acall(
            qdrant_search,
            qdrant_url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            collection=settings.qdrant_collection,
            user_query=user_query,
            company=company,
            year=year,
            limit=5,
        )
    except CircuitOpenError:
        logger.warning("qdrant 회로 차단 — fallback 사용")
        counter_inc("circuit_breaker_open_total", 1.0, {"target": "qdrant"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant 조회 실패: %s", exc)
        counter_inc("retrieval_errors_total", 1.0, {"target": "qdrant"})

    try:
        graph_results = await NEO4J_BREAKER.acall(
            neo4j_two_hop,
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            company=company,
        )
    except CircuitOpenError:
        logger.warning("neo4j 회로 차단 — fallback 사용")
        counter_inc("circuit_breaker_open_total", 1.0, {"target": "neo4j"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("neo4j 조회 실패: %s", exc)
        counter_inc("retrieval_errors_total", 1.0, {"target": "neo4j"})

    return vector_results, graph_results


async def hybrid_retrieve(
    user_query: str,
    *,
    company: str | None = None,
    year: int | None = None,
    plan: QueryPlan | None = None,
) -> Dict[str, Any]:
    """Fallback-first retrieval. Sprint 2 에서 Query Planner 와 Evidence 출력을 추가했다.

    하위호환: 기존 키(``vector_results``, ``graph_results``, ``raw``,
    ``analysis_context``, ``mode``, ``query``)는 그대로 유지된다.
    신규 키: ``evidence``(list of ``Evidence.model_dump()``), ``plan``.
    """
    if company is None or year is None:
        parsed_company, parsed_year = extract_company_year(user_query)
        company = company or parsed_company
        year = year or parsed_year

    if plan is None:
        plan = await plan_query(user_query)

    if plan.overall_intent == "out_of_scope":
        analysis_context = {
            "financial_facts": {"company_name": company or "UNKNOWN", "year": year or 0, "has_financial_data": False},
            "key_disclosures": [],
            "graph_signals": {"nodes": [], "edges": []},
            "data_quality": {"mode": "out_of_scope", "flags": ["out_of_scope"], "has_financial_data": False, "has_disclosures": False},
            "query_plan": plan.model_dump(),
        }
        return {
            "query": user_query,
            "vector_results": [],
            "graph_results": {"nodes": [], "edges": []},
            "raw": {"name": company or "UNKNOWN", "year": year or 0},
            "analysis_context": analysis_context,
            "mode": "out_of_scope",
            "evidence": [],
            "plan": plan.model_dump(),
        }

    if settings.has_real_retrieval:
        # Sprint 2: 단일 질의 기반 호출(병렬화 hook 만 마련). Sprint 3 에서 sub query 별 병렬 검색 도입.
        vector_results, graph_results = await _run_real_retrieval(
            user_query, company=company, year=year
        )

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
                plan=plan,
            )
            evidence = _hits_to_evidence(vector_results) + _graph_to_evidence(graph_results, company)
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
                "evidence": evidence,
                "plan": plan.model_dump(),
            }

    # ---- fallback (seed) ----
    seed = _load_seed()
    companies = seed.get("companies", [])
    target = companies[0] if companies else {}
    seed_vector = [
        {
            "chunk_id": "seed-001",
            "source_type": "DART_REPORT",
            "company_name": target.get("name", "UNKNOWN"),
            "year": target.get("year", 2024),
            "text_content": f"{target.get('name', '기업')} 재무/공시 요약",
        }
    ]
    seed_graph = {"nodes": [target.get("name", "Company")], "edges": ["HAS_REPORT", "INVOLVED_IN"]}
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
        "graph_signals": seed_graph,
        "data_quality": {
            "mode": "fallback",
            "flags": ["seed_fallback"],
            "has_financial_data": True,
            "has_disclosures": bool(target.get("disclosures")),
        },
        "query_plan": plan.model_dump(),
    }
    evidence = _hits_to_evidence(seed_vector) + _graph_to_evidence(seed_graph, target.get("name"))
    return {
        "query": user_query,
        "vector_results": seed_vector,
        "graph_results": seed_graph,
        "raw": {
            **target,
            "financial_facts": analysis_context["financial_facts"],
            "data_quality": analysis_context["data_quality"],
        },
        "analysis_context": analysis_context,
        "mode": "fallback",
        "evidence": evidence,
        "plan": plan.model_dump(),
    }


__all__ = ["hybrid_retrieve"]
