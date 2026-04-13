from __future__ import annotations

import random
import asyncio
import json
from typing import Any

import httpx

from app.config import settings


async def extract_finance_metrics(context: dict[str, Any]) -> dict[str, Any]:
    if not settings.has_real_llm:
        analysis_context = context.get("analysis_context", {})
        financial_facts = analysis_context.get("financial_facts", {})
        data_quality = analysis_context.get("data_quality", {})
        debt_ratio = financial_facts.get("debt_ratio", 0) or 0
        flags = data_quality.get("flags", [])
        if not financial_facts.get("has_financial_data") or "financial_parse_failed" in flags:
            insight = "재무 데이터가 충분하지 않아 정량 판단을 보류해야 합니다."
        else:
            insight = "부채비율 안정" if debt_ratio < 150 else "부채비율 상승으로 재무 리스크 존재"
        return {
            "debt_ratio": debt_ratio,
            "insight": insight,
            "has_sufficient_data": bool(financial_facts.get("has_financial_data")),
            "data_quality": ", ".join(flags) if flags else "ok",
            "source": "fallback",
        }

    analysis_context = context.get("analysis_context", {})
    prompt = (
        "당신은 재무 분석가입니다. 아래 analysis_context만 근거로 판단하세요. "
        "질문 연도와 회사에 해당하는 정보만 우선 사용하고, 데이터가 비어 있거나 0이어도 "
        "data_quality.flags에 missing/failed/partial이 있으면 실제 값이 아니라 누락 가능성으로 해석하세요. "
        "근거 없는 추정, 과장, 단정은 금지합니다. "
        "출력은 JSON 객체만 허용합니다. 키는 debt_ratio(숫자), insight(문자열), "
        "has_sufficient_data(불리언), data_quality(문자열)만 포함하세요. "
        "insight는 1~2문장으로 작성하고, 데이터가 부족하면 그 사실을 먼저 밝히세요. "
        f"analysis_context: {json.dumps(analysis_context, ensure_ascii=False)}"
    )
    
    url = settings.llm_base_url
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    async with httpx.AsyncClient(timeout=20) as client:
        max_retries = 3
        for attempt in range(max_retries):
            await asyncio.sleep(2.0)
            resp = await client.post(url, headers=headers, json=payload, timeout=120.0)
            
            if resp.status_code == 429 and attempt < max_retries - 1:
                # 기본 대기 시간을 늘리고, 병렬 충돌 방지를 위해 0~2초의 난수(Jitter) 주입
                wait_time = (2 ** attempt) * 2.5 + random.uniform(0, 2)
                print(f"[System] 429 할당량 초과. {wait_time:.2f}초 대기 후 재시도... (Attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
                
            resp.raise_for_status()
            break
            
        data = resp.json()
        
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # LLM 반환 텍스트를 실제 JSON 객체로 변환
    try:
        clean_text = text.strip().strip("```json").strip("```").strip()
        parsed_data = json.loads(clean_text)
        parsed_data["source"] = "real_llm"
        return parsed_data
    except Exception as e:
        print(f"[Warning] 재무 지표 JSON 파싱 실패: {e}")
        return {"debt_ratio": 0, "insight": text, "source": "parse_error"}


async def extract_risk_points(context: dict[str, Any]) -> list[str]:
    if not settings.has_real_llm:
        disclosures = context.get("analysis_context", {}).get("key_disclosures", [])
        return [f"{d.get('event_type')}: {d.get('summary')}" for d in disclosures] or ["중대 공시 리스크 미탐지"]

    analysis_context = context.get("analysis_context", {})
    prompt = (
        "당신은 리스크 분석가입니다. 아래 analysis_context 중 key_disclosures와 data_quality만 근거로 판단하세요. "
        "구체적 공시 근거가 없는 일반론적 경고는 쓰지 마세요. "
        "데이터가 부족하면 '공시 정보가 충분하지 않다'는 식의 신중한 문장 1개만 반환할 수 있습니다. "
        "출력은 JSON 배열(Array)만 허용합니다. 각 항목은 짧고 구체적인 리스크 문장이어야 합니다. "
        f"analysis_context: {json.dumps(analysis_context, ensure_ascii=False)}"
    )
    
    url = settings.llm_base_url
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    async with httpx.AsyncClient(timeout=20) as client:
        max_retries = 3
        for attempt in range(max_retries):
            await asyncio.sleep(2.0)
            resp = await client.post(url, headers=headers, json=payload, timeout=120.0)
            
            if resp.status_code == 429 and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[System] 429 Rate Limit 감지. {wait_time}초 대기 후 재시도합니다... (Attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
                
            resp.raise_for_status()
            break
            
        data = resp.json()
        
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # LLM 반환 텍스트를 실제 리스트 객체로 변환
    try:
        clean_text = text.strip().strip("```json").strip("```").strip()
        parsed_array = json.loads(clean_text)
        if isinstance(parsed_array, list):
            return parsed_array
        return [text]
    except Exception as e:
        print(f"[Warning] 리스크 포인트 JSON 파싱 실패: {e}")
        return [text] if text else ["리스크 응답 없음"]