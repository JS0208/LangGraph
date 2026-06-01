"""Structured LLM extractors using PromptRegistry — with real-time token streaming."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.streaming import active_thread, put_token
from app.config import settings
from app.llm.providers.base import LLMRequest
from app.llm.router import LLMRouter, get_router

logger = logging.getLogger(__name__)


def _build_finance_prompt(analysis_context: dict) -> str:
    try:
        from app.prompts import get_registry
        return get_registry().render(
            "finance_metrics",
            analysis_context=json.dumps(analysis_context, ensure_ascii=False),
        )
    except Exception:
        return (
            "You are a financial analyst. Use only the analysis_context below.\n"
            "Output JSON only with keys: debt_ratio(number), insight(string), "
            "has_sufficient_data(bool), data_quality(string).\n"
            "analysis_context: " + json.dumps(analysis_context, ensure_ascii=False)
        )


def _build_risk_prompt(analysis_context: dict) -> str:
    try:
        from app.prompts import get_registry
        return get_registry().render(
            "risk_points",
            analysis_context=json.dumps(analysis_context, ensure_ascii=False),
        )
    except Exception:
        return (
            "You are a risk analyst. Use only key_disclosures and data_quality.\n"
            "Output JSON array only. Each item is a concise risk sentence.\n"
            "analysis_context: " + json.dumps(analysis_context, ensure_ascii=False)
        )


def _strip_json_envelope(text: str) -> str:
    return text.strip().strip("```json").strip("```").strip()


def _fallback_finance(analysis_context: dict) -> dict:
    financial_facts = analysis_context.get("financial_facts", {})
    data_quality = analysis_context.get("data_quality", {})
    debt_ratio = financial_facts.get("debt_ratio", 0) or 0
    flags = data_quality.get("flags", [])
    if not financial_facts.get("has_financial_data") or "financial_parse_failed" in flags:
        insight = "Financial data is insufficient for quantitative judgment."
    else:
        insight = "Debt ratio stable" if debt_ratio < 150 else "Debt ratio elevated -- financial risk exists"
    return {
        "debt_ratio": debt_ratio,
        "insight": insight,
        "has_sufficient_data": bool(financial_facts.get("has_financial_data")),
        "data_quality": ", ".join(flags) if flags else "ok",
        "source": "fallback",
    }


def _fallback_risk(analysis_context: dict) -> list:
    disclosures = analysis_context.get("key_disclosures", [])
    items = ["{}: {}".format(d.get("event_type"), d.get("summary")) for d in disclosures]
    return items or ["No significant disclosure risk detected"]


async def _stream_to_buffer(
    router: LLMRouter,
    intent: str,
    request: LLMRequest,
    node_name: str,
) -> str:
    """Stream tokens from LLM, push each token to SSE buffer, return full text.

    Falls back to router.invoke() if streaming fails or thread_id is unset.
    """
    thread_id = active_thread()
    full_text = ""
    try:
        async for token in router.stream(intent, request):
            full_text += token
            if thread_id:
                put_token(thread_id, node_name, token)
        return full_text
    except Exception as exc:
        logger.warning("streaming failed for intent %s (%s) -- invoke fallback", intent, exc)
        # Fallback to blocking invoke
        response = await router.invoke(intent, request)
        return response.text


async def extract_finance_metrics(
    context: dict,
    *,
    router: LLMRouter | None = None,
) -> dict:
    analysis_context = context.get("analysis_context", {})
    if not settings.has_real_llm:
        return _fallback_finance(analysis_context)
    router = router or get_router()
    request = LLMRequest(prompt=_build_finance_prompt(analysis_context), temperature=0.0, json_mode=True)
    try:
        raw_text = await _stream_to_buffer(router, "finance_metrics", request, "finance_analyst")
    except Exception as exc:
        logger.warning("finance LLM call failed (%s) -- fallback", exc)
        return _fallback_finance(analysis_context)
    try:
        parsed: dict = json.loads(_strip_json_envelope(raw_text))
        parsed["source"] = "real_llm" if router.select_provider("finance_metrics").name != "mock" else "mock"
        return parsed
    except Exception as exc:
        logger.warning("finance JSON parse failed (%s) -- raw text", exc)
        return {"debt_ratio": 0, "insight": raw_text, "source": "parse_error"}


async def extract_risk_points(
    context: dict,
    *,
    router: LLMRouter | None = None,
) -> list:
    analysis_context = context.get("analysis_context", {})
    if not settings.has_real_llm:
        return _fallback_risk(analysis_context)
    router = router or get_router()
    request = LLMRequest(prompt=_build_risk_prompt(analysis_context), temperature=0.0, json_mode=True)
    try:
        raw_text = await _stream_to_buffer(router, "risk_points", request, "risk_compliance")
    except Exception as exc:
        logger.warning("risk LLM call failed (%s) -- fallback", exc)
        return _fallback_risk(analysis_context)
    try:
        parsed = json.loads(_strip_json_envelope(raw_text))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [raw_text]
    except Exception as exc:
        logger.warning("risk JSON parse failed (%s) -- raw text", exc)
        return [raw_text] if raw_text else ["No risk response"]


__all__ = ["extract_finance_metrics", "extract_risk_points"]
