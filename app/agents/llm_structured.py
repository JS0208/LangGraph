from __future__ import annotations

from typing import Any

from app.config import settings


async def extract_finance_metrics(context: dict[str, Any]) -> dict[str, Any]:
    if not settings.has_real_llm:
        raw = context.get("raw", {})
        debt_ratio = raw.get("debt_ratio", 0)
        insight = "부채비율 안정" if debt_ratio < 150 else "부채비율 상승으로 재무 리스크 존재"
        return {"debt_ratio": debt_ratio, "insight": insight, "source": "fallback"}

    prompt = (
        "다음 컨텍스트를 보고 JSON으로만 답하세요."
        "키는 debt_ratio(number), insight(string). 컨텍스트: "
        f"{context}"
    )
    body = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.llm_base_url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"insight": text, "source": "real_llm"}


async def extract_risk_points(context: dict[str, Any]) -> list[str]:
    if not settings.has_real_llm:
        disclosures = context.get("raw", {}).get("disclosures", [])
        return [f"{d.get('event_type')}: {d.get('summary')}" for d in disclosures] or ["중대 공시 리스크 미탐지"]

    prompt = (
        "다음 컨텍스트를 보고 리스크 포인트를 JSON 배열 문자열로 반환하세요."
        f"컨텍스트: {context}"
    )
    body = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.llm_base_url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return [text] if text else ["리스크 응답 없음"]
