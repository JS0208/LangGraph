"""OpenAI-호환 Chat Completions Provider (현행 ``llm_structured.py`` 와 동일한 호출 형식).

기존 코드가 이미 ``settings.llm_base_url`` 로 OpenAI-호환 엔드포인트를 호출했기 때문에,
같은 동작을 그대로 보존한 상태에서 Provider 추상화에 통합한다.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from app.config import settings
from app.llm.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.observability.metrics import counter_inc
from app.schemas import LLMUsage
from app.utils.circuit import CircuitBreaker, CircuitOpenError
from app.utils.retry import async_retry


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._base_url = base_url if base_url is not None else settings.llm_base_url
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._model = model if model is not None else settings.llm_model
        self._timeout = timeout_s
        self._breaker = CircuitBreaker(
            name=f"llm:{self._model or 'unknown'}",
            failure_threshold=4,
            recovery_time_s=30.0,
        )

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    @async_retry(max_attempts=3, base_delay=2.0, max_delay=20.0)
    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._base_url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def _post_guarded(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._breaker.acall(self._post, payload)
        except CircuitOpenError as exc:
            counter_inc("circuit_breaker_open_total", 1.0, {"target": "llm"})
            raise RuntimeError("LLM circuit is open") from exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.available:
            raise RuntimeError("OpenAICompatProvider is not available (missing base_url/api_key/model)")

        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        started = time.perf_counter()
        data = await self._post_guarded(payload)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage_dict = data.get("usage", {}) or {}
        usage = LLMUsage(
            model=self._model,
            prompt_tokens=int(usage_dict.get("prompt_tokens", 0)),
            completion_tokens=int(usage_dict.get("completion_tokens", 0)),
            total_tokens=int(usage_dict.get("total_tokens", 0)),
            cost_usd=0.0,  # Sprint 4의 Cost Calculator에서 채움
            latency_ms=elapsed_ms,
            cached=False,
        )
        return LLMResponse(text=text, usage=usage, raw=data)

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """OpenAI-호환 SSE chat completions stream.

        Provider 가 실연동 가능한 경우 token delta 를 그대로 yield 한다.
        실패 시 ``complete`` 결과를 단어 단위 yield 하는 안전 fallback 을 사용.
        """
        if not self.available:
            response = await self.complete(request)
            for chunk in response.text.split(" "):
                if chunk:
                    yield chunk + " "
            return

        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", self._base_url, headers=headers, json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content")
                        )
                        if delta:
                            yield delta
        except Exception:
            # 진짜 stream 실패 시 안전 fallback.
            response = await self.complete(request)
            for chunk in response.text.split(" "):
                if chunk:
                    yield chunk + " "

    @staticmethod
    def parse_json_response(text: str) -> Any:
        """현행 ``llm_structured.py`` 와 동일한 JSON 정제 규칙."""
        clean = text.strip().strip("```json").strip("```").strip()
        return json.loads(clean)


__all__ = ["OpenAICompatProvider"]
