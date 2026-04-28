"""LLMRouter <-> llm_structured 통합 회귀.

목적: ``settings.has_real_llm`` 가 True 인 환경에서도 Router 경유 경로가
기존 dict/list 포맷을 깨지 않는지 확인한다.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.agents import llm_structured
from app.llm.providers import LLMRequest, MockProvider
from app.llm.providers.base import LLMProvider, LLMResponse
from app.llm.router import LLMRouter
from app.schemas import LLMUsage


class _StaticProvider(LLMProvider):
    name = "static"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    @property
    def available(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        return LLMResponse(text=self._payload, usage=LLMUsage(model="static"))


def _force_real_llm(monkeypatch) -> None:
    """frozen dataclass 인 settings 를 SimpleNamespace 로 교체해 has_real_llm 을 True 로 강제."""
    fake = SimpleNamespace(has_real_llm=True)
    monkeypatch.setattr(llm_structured, "settings", fake)


def test_finance_extractor_uses_router_when_real_llm_enabled(monkeypatch):
    finance_payload = json.dumps(
        {
            "debt_ratio": 220.5,
            "insight": "단기 차입 증가로 부채비율 상승",
            "has_sufficient_data": True,
            "data_quality": "ok",
        },
        ensure_ascii=False,
    )
    router = LLMRouter(
        primary=MockProvider(),
        mock=MockProvider(),
        provider_overrides={"finance_metrics": _StaticProvider(finance_payload)},
    )

    _force_real_llm(monkeypatch)
    ctx = {
        "analysis_context": {
            "financial_facts": {"debt_ratio": 220, "has_financial_data": True},
            "data_quality": {"flags": []},
        }
    }
    result = asyncio.run(llm_structured.extract_finance_metrics(ctx, router=router))
    assert result["debt_ratio"] == 220.5
    assert "부채비율" in result["insight"]


def test_risk_extractor_uses_router_when_real_llm_enabled(monkeypatch):
    payload = json.dumps(["규제 조사 진행", "유상증자 결정"], ensure_ascii=False)
    router = LLMRouter(
        primary=MockProvider(),
        mock=MockProvider(),
        provider_overrides={"risk_points": _StaticProvider(payload)},
    )

    _force_real_llm(monkeypatch)
    ctx = {
        "analysis_context": {
            "key_disclosures": [{"event_type": "REGULATION", "summary": "조사"}],
        }
    }
    result = asyncio.run(llm_structured.extract_risk_points(ctx, router=router))
    assert result == ["규제 조사 진행", "유상증자 결정"]


def test_finance_extractor_falls_back_when_router_fails(monkeypatch):
    class _Boom(LLMProvider):
        name = "boom"

        @property
        def available(self) -> bool:
            return True

        async def complete(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
            raise RuntimeError("primary down")

    class _BoomMock(LLMProvider):
        name = "mock"

        @property
        def available(self) -> bool:
            return True

        async def complete(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
            raise RuntimeError("mock down")

    router = LLMRouter(primary=_Boom(), mock=_BoomMock())
    _force_real_llm(monkeypatch)

    ctx = {
        "analysis_context": {
            "financial_facts": {"debt_ratio": 100, "has_financial_data": True},
            "data_quality": {"flags": []},
        }
    }
    result = asyncio.run(llm_structured.extract_finance_metrics(ctx, router=router))
    # Router 양단 모두 실패하면 fallback 분석으로 회귀해야 한다.
    assert result["source"] == "fallback"
    assert result["debt_ratio"] == 100
