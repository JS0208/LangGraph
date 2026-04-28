"""LLMRouter — Sprint 1.

역할
- intent ("finance_metrics", "risk_points", "planner", "critic", "generic") 별로
  적절한 Provider 를 골라 ``invoke()`` 한다.
- 키가 비어 있는 환경에서는 자동으로 ``MockProvider`` 로 우회한다 (fallback-first).
- Sprint 2 이후 Semantic Cache, Sprint 4 이후 Cost Budget 이 같은 진입점에 부착된다.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Mapping

from app.llm.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


KNOWN_INTENTS = {
    "generic",
    "finance_metrics",
    "risk_points",
    "planner",
    "critic",
    "intent_classifier",
    "reflexion",
}


class LLMRouter:
    """기본 Router — intent → provider 결정.

    현재(Sprint 1)는 단일 ``OpenAICompatProvider`` 또는 ``MockProvider`` 만 사용한다.
    Sprint 4에서 reasoning vs extraction 분리, Semantic Cache, Budget 가드를
    같은 클래스 내부에 흡수한다.
    """

    def __init__(
        self,
        primary: LLMProvider | None = None,
        mock: LLMProvider | None = None,
        provider_overrides: Mapping[str, LLMProvider] | None = None,
    ) -> None:
        self._primary = primary if primary is not None else OpenAICompatProvider()
        self._mock = mock if mock is not None else MockProvider()
        self._overrides: dict[str, LLMProvider] = dict(provider_overrides or {})

    def select_provider(self, intent: str) -> LLMProvider:
        if intent in self._overrides:
            return self._overrides[intent]
        if self._primary.available:
            return self._primary
        return self._mock

    async def invoke(self, intent: str, request: LLMRequest) -> LLMResponse:
        if intent not in KNOWN_INTENTS:
            logger.debug("unknown intent '%s' — defaulting to generic", intent)
            intent = "generic"

        # request.metadata 에 intent 를 항상 주입해 Mock/관측에 사용한다.
        request.metadata = {**request.metadata, "intent": intent}

        provider = self.select_provider(intent)
        try:
            response = await provider.complete(request)
        except Exception as exc:  # noqa: BLE001
            # Provider 실패 시 안전하게 Mock 으로 한 번 더 폴백.
            if provider is self._mock:
                raise
            logger.warning(
                "primary provider '%s' failed for intent '%s' (%s); falling back to mock",
                provider.name,
                intent,
                exc,
            )
            response = await self._mock.complete(request)
        return response

    async def stream(self, intent: str, request: LLMRequest) -> AsyncIterator[str]:
        """토큰 단위 스트림. provider 가 실패하면 mock 으로 polyfill.

        주의: AsyncIterator 반환이라 caller 는 ``async for`` 로 소비한다.
        """
        if intent not in KNOWN_INTENTS:
            intent = "generic"
        request.metadata = {**request.metadata, "intent": intent}
        provider = self.select_provider(intent)
        try:
            async for token in provider.astream(request):
                yield token
            return
        except Exception as exc:  # noqa: BLE001
            if provider is self._mock:
                raise
            logger.warning(
                "primary provider '%s' streaming failed for intent '%s' (%s); falling back to mock",
                provider.name,
                intent,
                exc,
            )
        async for token in self._mock.astream(request):
            yield token


_singleton: LLMRouter | None = None


def get_router() -> LLMRouter:
    """프로세스 단일 인스턴스. 테스트는 ``LLMRouter()`` 로 직접 생성해도 된다."""
    global _singleton
    if _singleton is None:
        _singleton = LLMRouter()
    return _singleton


def reset_router() -> None:
    """테스트 헬퍼."""
    global _singleton
    _singleton = None


__all__ = ["LLMRouter", "get_router", "reset_router", "KNOWN_INTENTS"]
