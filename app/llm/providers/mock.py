"""결정론적(Deterministic) Mock Provider — 테스트 및 fallback 용.

키가 없거나 외부 호출을 막아야 할 때 사용한다.
응답은 입력 prompt 와 metadata 에 의해 결정론적으로 생성된다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, AsyncIterator

from app.llm.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.schemas import LLMUsage


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, fixed_responses: dict[str, str] | None = None) -> None:
        self._fixed = fixed_responses or {}

    @property
    def available(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        intent = request.metadata.get("intent", "generic")
        # 키가 등록된 intent 에 대해서는 고정 응답을 반환 (테스트 결정성).
        if intent in self._fixed:
            text = self._fixed[intent]
        else:
            text = self._synthesize(request, intent)

        digest = hashlib.sha1(request.prompt.encode("utf-8")).hexdigest()[:8]
        usage = LLMUsage(
            model=f"mock-{intent}",
            prompt_tokens=len(request.prompt.split()),
            completion_tokens=len(text.split()),
            total_tokens=len(request.prompt.split()) + len(text.split()),
            cost_usd=0.0,
            latency_ms=0.5,
            cached=False,
        )
        return LLMResponse(text=text, usage=usage, raw={"digest": digest, "mock": True})

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        # 결정론적 토큰 청크 (공백 단위, 빈 청크 제외).
        for token in response.text.split(" "):
            if token:
                yield token + " "

    @staticmethod
    def _synthesize(request: LLMRequest, intent: str) -> str:
        if intent == "finance_metrics":
            payload: dict[str, Any] = {
                "debt_ratio": 0.0,
                "insight": "MOCK 응답 — 실 LLM 키가 비어 있어 기본 fallback 분석을 반환합니다.",
                "has_sufficient_data": False,
                "data_quality": "mock",
            }
            return json.dumps(payload, ensure_ascii=False)
        if intent == "risk_points":
            return json.dumps(["MOCK: 공시 정보가 충분하지 않아 리스크 단정이 어렵습니다."], ensure_ascii=False)
        if request.json_mode:
            return json.dumps({"text": "mock", "intent": intent}, ensure_ascii=False)
        return f"[MOCK:{intent}] {request.prompt[:80]}"


__all__ = ["MockProvider"]
