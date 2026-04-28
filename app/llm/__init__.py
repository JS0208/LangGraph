"""LLM Layer 패키지 (Sprint 1).

핵심 진입점은 ``LLMRouter.invoke(intent=..., ...)`` 다.
모든 직호출(httpx 등)은 점진적으로 이 모듈로 이전된다.
"""

from app.llm.router import LLMRouter, get_router

__all__ = ["LLMRouter", "get_router"]
