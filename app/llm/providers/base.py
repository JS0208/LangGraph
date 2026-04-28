"""LLM Provider 추상 인터페이스 — Sprint 1.

Sprint 6 에서 ``astream`` 토큰 단위 인터페이스가 추가되었다.
기본 구현은 ``complete`` 응답을 공백 단위로 yield 하는 fallback.
진짜 SSE 토큰 streaming 은 ``OpenAICompatProvider.astream`` 에서 구현된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.schemas import LLMUsage


@dataclass
class LLMRequest:
    prompt: str
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    json_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class LLMProvider(ABC):
    """모든 provider 가 구현해야 할 최소 인터페이스."""

    name: str = "unknown"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """단발성 completion."""

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """토큰 단위 비동기 스트림. 기본은 ``complete`` 결과를 단어 단위 yield.

        Provider 가 진짜 SSE 토큰 stream 을 지원하면 이 메서드를 override 한다.
        """
        response = await self.complete(request)
        for chunk in response.text.split(" "):
            if chunk:
                yield chunk + " "

    @property
    def available(self) -> bool:
        """provider 가 사용 가능한 상태인지 (키/엔드포인트 점검)."""
        return True


__all__ = ["LLMProvider", "LLMRequest", "LLMResponse"]
