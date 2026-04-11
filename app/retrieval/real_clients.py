from __future__ import annotations

import importlib.util
import re
from typing import Any


def _extract_company_and_year(user_query: str) -> tuple[str | None, int | None]:
    companies = ["삼성전자", "SK하이닉스", "네이버", "카카오", "LG CNS"]
    company = next((c for c in companies if c in user_query), None)
    year = None
    match = re.search(r"(19|20)\d{2}", user_query)
    if match:
        year = int(match.group(0))
    return company, year


async def qdrant_search(
    qdrant_url: str,
    api_key: str,
    collection: str,
    user_query: str,
    company: str | None,
    year: int | None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    payload_filter: dict[str, Any] = {"must": []}
    if company:
        payload_filter["must"].append({"key": "company_name", "match": {"value": company}})
    if year:
        payload_filter["must"].append({"key": "year", "match": {"value": year}})

    body: dict[str, Any] = {
        "query": user_query,
        "limit": limit,
        "with_payload": True,
    }
    if payload_filter["must"]:
        body["filter"] = payload_filter

    url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/query"
    headers = {"api-key": api_key}
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json().get("result", [])

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
        "MATCH (c:Company {name: $name})-[r*1..2]-(n) "
        "RETURN collect(distinct c.name) + collect(distinct n.name) AS nodes, "
        "[rel in relationships(apoc.coll.flatten(r))[..20] | type(rel)] AS edges"
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
