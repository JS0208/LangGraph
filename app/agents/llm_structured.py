"""구조화 LLM 추출기 — Sprint 1 리팩터.

변경점
- 모든 외부 LLM 호출은 ``LLMRouter`` 를 거친다 (`app/llm/router.py`).
- 키가 비어 있는 fallback 경로의 결과는 **거동/포맷 모두 기존과 동일**.
- 실 LLM 경로의 결과 또한 기존과 동일한 dict / list 포맷을 반환한다.
- 신규 Pydantic 모델(`FinanceMetrics` 등)은 점진적 도입을 위해 어댑터 함수로만 노출한다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.llm.providers.base import LLMRequest
from app.llm.router import LLMRouter, get_router

logger = logging.getLogger(__name__)


def _build_finance_prompt(analysis_context: dict[str, Any]) -> str:
    return (
        "당신은 재무 분석가입니다. 아래 analysis_context만 근거로 판단하세요. "
        "질문 연도와 회사에 해당하는 정보만 우선 사용하고, 데이터가 비어 있거나 0이어도 "
        "data_quality.flags에 missing/failed/partial이 있으면 실제 값이 아니라 누락 가능성으로 해석하세요. "
        "근거 없는 추정, 과장, 단정은 금지합니다. "
        "출력은 JSON 객체만 허용합니다. 키는 debt_ratio(숫자), insight(문자열), "
        "has_sufficient_data(불리언), data_quality(문자열)만 포함하세요. "
        "insight는 1~2문장으로 작성하고, 데이터가 부족하면 그 사실을 먼저 밝히세요. "
        f"analysis_context: {json.dumps(analysis_context, ensure_ascii=False)}"
    )


def _build_risk_prompt(analysis_context: dict[str, Any]) -> str:
    return (
        "당신은 리스크 분석가입니다. 아래 analysis_context 중 key_disclosures와 data_quality만 근거로 판단하세요. "
        "구체적 공시 근거가 없는 일반론적 경고는 쓰지 마세요. "
        "데이터가 부족하면 '공시 정보가 충분하지 않다'는 식의 신중한 문장 1개만 반환할 수 있습니다. "
        "출력은 JSON 배열(Array)만 허용합니다. 각 항목은 짧고 구체적인 리스크 문장이어야 합니다. "
        f"analysis_context: {json.dumps(analysis_context, ensure_ascii=False)}"
    )


def _strip_json_envelope(text: str) -> str:
    return text.strip().strip("```json").strip("```").strip()


def _fallback_finance(analysis_context: dict[str, Any]) -> dict[str, Any]:
    """기존 fallback 거동(키 없는 환경)을 그대로 보존."""
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


def _fallback_risk(analysis_context: dict[str, Any]) -> list[str]:
    disclosures = analysis_context.get("key_disclosures", [])
    items = [f"{d.get('event_type')}: {d.get('summary')}" for d in disclosures]
    return items or ["중대 공시 리스크 미탐지"]


async def extract_finance_metrics(
    context: dict[str, Any],
    *,
    router: LLMRouter | None = None,
) -> dict[str, Any]:
    """재무 지표 추출. 키 없는 환경에서는 fallback 출력을 그대로 반환."""
    analysis_context = context.get("analysis_context", {})

    if not settings.has_real_llm:
        return _fallback_finance(analysis_context)

    router = router or get_router()
    request = LLMRequest(
        prompt=_build_finance_prompt(analysis_context),
        temperature=0.0,
        json_mode=True,
    )
    try:
        response = await router.invoke("finance_metrics", request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("finance LLM 호출 실패 (%s) — fallback 으로 전환", exc)
        return _fallback_finance(analysis_context)

    try:
        parsed: dict[str, Any] = json.loads(_strip_json_envelope(response.text))
        parsed["source"] = "real_llm" if router.select_provider("finance_metrics").name != "mock" else "mock"
        return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("finance JSON 파싱 실패 (%s) — raw text 로 회귀", exc)
        return {"debt_ratio": 0, "insight": response.text, "source": "parse_error"}


async def extract_risk_points(
    context: dict[str, Any],
    *,
    router: LLMRouter | None = None,
) -> list[str]:
    """리스크 포인트 추출. 키 없는 환경에서는 fallback 출력을 그대로 반환."""
    analysis_context = context.get("analysis_context", {})

    if not settings.has_real_llm:
        return _fallback_risk(analysis_context)

    router = router or get_router()
    request = LLMRequest(
        prompt=_build_risk_prompt(analysis_context),
        temperature=0.0,
        json_mode=True,
    )
    try:
        response = await router.invoke("risk_points", request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk LLM 호출 실패 (%s) — fallback 으로 전환", exc)
        return _fallback_risk(analysis_context)

    try:
        parsed = json.loads(_strip_json_envelope(response.text))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [response.text]
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk JSON 파싱 실패 (%s) — raw text 로 회귀", exc)
        return [response.text] if response.text else ["리스크 응답 없음"]


__all__ = ["extract_finance_metrics", "extract_risk_points"]
