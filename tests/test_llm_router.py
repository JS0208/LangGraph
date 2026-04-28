from __future__ import annotations

import asyncio
import json

import pytest

from app.llm.providers import LLMRequest, MockProvider
from app.llm.providers.base import LLMProvider, LLMResponse
from app.llm.router import KNOWN_INTENTS, LLMRouter
from app.schemas import LLMUsage


class _FailingProvider(LLMProvider):
    name = "failing"

    @property
    def available(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        raise RuntimeError("primary down")


class _UnavailableProvider(LLMProvider):
    name = "unavailable"

    @property
    def available(self) -> bool:
        return False

    async def complete(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        raise RuntimeError("should not be called")


def test_router_uses_mock_when_primary_unavailable():
    router = LLMRouter(primary=_UnavailableProvider(), mock=MockProvider())
    response = asyncio.run(router.invoke("finance_metrics", LLMRequest(prompt="x")))
    payload = json.loads(response.text)
    assert "debt_ratio" in payload
    assert response.usage.model.startswith("mock-")


def test_router_falls_back_when_primary_raises():
    router = LLMRouter(primary=_FailingProvider(), mock=MockProvider())
    response = asyncio.run(router.invoke("risk_points", LLMRequest(prompt="x")))
    parsed = json.loads(response.text)
    assert isinstance(parsed, list)


def test_router_normalizes_unknown_intent_to_generic():
    router = LLMRouter(primary=_UnavailableProvider(), mock=MockProvider())
    response = asyncio.run(router.invoke("nonsense_intent", LLMRequest(prompt="hello")))
    assert response.text  # generic mock 은 비어있지 않다.


def test_router_provider_overrides_take_priority():
    captured: dict[str, LLMRequest] = {}

    class _CaptureProvider(LLMProvider):
        name = "capture"

        @property
        def available(self) -> bool:
            return True

        async def complete(self, request: LLMRequest) -> LLMResponse:
            captured["req"] = request
            return LLMResponse(text="captured", usage=LLMUsage(model="capture"))

    router = LLMRouter(
        primary=MockProvider(),
        mock=MockProvider(),
        provider_overrides={"finance_metrics": _CaptureProvider()},
    )
    response = asyncio.run(router.invoke("finance_metrics", LLMRequest(prompt="hi")))
    assert response.text == "captured"
    assert captured["req"].metadata.get("intent") == "finance_metrics"


def test_known_intents_includes_core():
    assert {"finance_metrics", "risk_points", "planner", "critic"} <= KNOWN_INTENTS
