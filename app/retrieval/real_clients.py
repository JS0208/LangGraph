from __future__ import annotations

import importlib.util
import re
from typing import Any

import httpx

from app.config import settings

VECTOR_SIZE = 768
COMPANY_ALIAS_MAP = {
    "삼성전자": "삼성전자",
    "samsungelectronics": "삼성전자",
    "samsungelectronics": "삼성전자",
    "sk하이닉스": "SK하이닉스",
    "sk hynix": "SK하이닉스",
    "skhynix": "SK하이닉스",
    "네이버": "NAVER",
    "naver": "NAVER",
    "카카오": "카카오",
    "kakao": "카카오",
    "lg cns": "LG CNS",
    "lgcns": "LG CNS",
    "엘지cns": "LG CNS",
}


def _normalize_company_text(text: str) -> str:
    return re.sub(r"[\s\-_()]+", "", text).lower()


def _payload_richness(payload: dict[str, Any]) -> int:
    keys = (
        "quarter",
        "revenue",
        "operating_profit",
        "debt_ratio",
        "has_financial_data",
        "date",
        "event_type",
        "summary",
    )
    score = 0
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", []):
            score += 1
    return score


def _extract_company_and_year(user_query: str) -> tuple[str | None, int | None]:
    lowered_query = user_query.lower()
    normalized_query = _normalize_company_text(user_query)

    company = None
    for alias, canonical in sorted(COMPANY_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        alias_lower = alias.lower()
        alias_normalized = _normalize_company_text(alias)
        if alias_lower in lowered_query or alias_normalized in normalized_query:
            company = canonical
            break

    year = None
    match = re.search(r"(19|20)\d{2}", user_query)
    if match:
        year = int(match.group(0))
    return company, year


async def _embed_query(user_query: str) -> list[float]:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for real Qdrant search")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/gemini-embedding-001:embedContent?key={settings.llm_api_key}"
    )
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": user_query}]},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        values = resp.json()["embedding"]["values"]
        if len(values) >= VECTOR_SIZE:
            return values[:VECTOR_SIZE]
        return values + [0.0] * (VECTOR_SIZE - len(values))


async def qdrant_search(
    qdrant_url: str,
    api_key: str,
    collection: str,
    user_query: str,
    company: str | None,
    year: int | None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    search_url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/search"
    scroll_url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll"
    headers = {"api-key": api_key}

    async def _post_query(body: dict[str, Any]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(search_url, json=body, headers=headers)
            if resp.status_code == 400 and body.get("filter"):
                error_text = resp.text
                if "Index required" in error_text:
                    fallback_body = dict(body)
                    fallback_body.pop("filter", None)
                    retry = await client.post(search_url, json=fallback_body, headers=headers)
                    retry.raise_for_status()
                    raw_result = retry.json().get("result", [])
                else:
                    resp.raise_for_status()
            else:
                resp.raise_for_status()
                raw_result = resp.json().get("result", [])

        if isinstance(raw_result, dict):
            return raw_result.get("points") or raw_result.get("hits") or []
        return raw_result

    async def _scroll_query(filter_body: dict[str, Any], fallback_limit: int) -> list[dict[str, Any]]:
        body = {
            "limit": max(fallback_limit, 10),
            "with_payload": True,
            "filter": filter_body,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(scroll_url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json().get("result", {}).get("points", [])

    async def _filtered_scroll_fallback(base_filter: dict[str, Any], fallback_limit: int) -> list[dict[str, Any]]:
        points = await _scroll_query(base_filter, max(fallback_limit * 4, 25))
        financial_points = [
            item for item in points if item.get("payload", {}).get("source_type") == "FINANCIAL_REPORT"
        ]
        disclosure_points = [
            item for item in points if item.get("payload", {}).get("source_type") == "DISCLOSURE"
        ]
        financial_points.sort(key=lambda item: _payload_richness(item.get("payload", {})), reverse=True)
        disclosure_points.sort(key=lambda item: _payload_richness(item.get("payload", {})), reverse=True)
        return [*financial_points[:1], *disclosure_points[: max(fallback_limit - 1, 1)]]

    payload_filter: dict[str, Any] = {"must": []}
    if company:
        payload_filter["must"].append({"key": "company_name", "match": {"value": company}})
    if year:
        payload_filter["must"].append({"key": "year", "match": {"value": year}})

    result: list[dict[str, Any]] = []
    try:
        query_vector = await _embed_query(user_query)
        body: dict[str, Any] = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
        }
        if payload_filter["must"]:
            body["filter"] = payload_filter
        result = await _post_query(body)
    except Exception:
        if payload_filter["must"]:
            result = await _filtered_scroll_fallback(payload_filter, limit)
        else:
            raise

    if not result and payload_filter["must"]:
        result = await _filtered_scroll_fallback(payload_filter, limit)

    normalized: list[dict[str, Any]] = []
    for item in result:
        payload = item.get("payload", {})
        normalized.append(
            {
                "chunk_id": str(item.get("id", "")),
                "source_type": payload.get("source_type", "DART_REPORT"),
                "company_name": payload.get("company_name", company or "UNKNOWN"),
                "year": payload.get("year", year or 0),
                "text_content": payload.get("text_content", ""),
                "quarter": payload.get("quarter"),
                "revenue": payload.get("revenue"),
                "operating_profit": payload.get("operating_profit"),
                "debt_ratio": payload.get("debt_ratio"),
                "has_financial_data": payload.get("has_financial_data"),
                "data_quality_flags": payload.get("data_quality_flags", []),
                "date": payload.get("date"),
                "event_type": payload.get("event_type"),
                "summary": payload.get("summary"),
                "retrieval_strategy": "semantic_search" if "score" in item else "filtered_scroll_fallback",
            }
        )
    return normalized


async def neo4j_two_hop(
    uri: str,
    user: str,
    password: str,
    company: str | None,
) -> dict[str, Any]:
    if not company:
        return {"nodes": [], "edges": []}

    if importlib.util.find_spec("neo4j") is None:
        raise RuntimeError("neo4j package is not installed")

    from neo4j import AsyncGraphDatabase

    query = (
        "MATCH p=(c:Company {name: $name})-[*1..2]-(n) "
        "UNWIND relationships(p) AS rel "
        "RETURN collect(DISTINCT c.name) + collect(DISTINCT n.name) AS nodes, "
        "collect(DISTINCT type(rel))[..20] AS edges"
    )
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            rec = await session.run(query, name=company)
            row = await rec.single()
            if not row:
                return {"nodes": [company], "edges": []}
            return {"nodes": row.get("nodes") or [company], "edges": row.get("edges") or []}
    finally:
        await driver.close()


def extract_company_year(user_query: str) -> tuple[str | None, int | None]:
    return _extract_company_and_year(user_query)
