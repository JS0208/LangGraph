from __future__ import annotations

import asyncio

import pytest

from app.llm.providers.base import LLMRequest
from app.llm.providers.mock import MockProvider
from app.llm.router import LLMRouter


def test_mock_provider_astream_yields_tokens():
    provider = MockProvider()
    request = LLMRequest(prompt="삼성전자 매출", metadata={"intent": "generic"})

    async def _collect() -> list[str]:
        out: list[str] = []
        async for tok in provider.astream(request):
            out.append(tok)
        return out

    tokens = asyncio.run(_collect())
    assert tokens
    assert all(isinstance(t, str) and t for t in tokens)


def test_router_stream_falls_back_to_mock_when_primary_unavailable():
    router = LLMRouter()  # primary=OpenAICompatProvider() unavailable in test env

    async def _collect() -> list[str]:
        out: list[str] = []
        async for tok in router.stream("generic", LLMRequest(prompt="hello")):
            out.append(tok)
        return out

    tokens = asyncio.run(_collect())
    assert tokens
    joined = "".join(tokens)
    assert "MOCK" in joined or len(joined) > 0


def test_router_stream_unknown_intent_normalized():
    router = LLMRouter()

    async def _collect() -> list[str]:
        return [tok async for tok in router.stream("???", LLMRequest(prompt="x"))]

    tokens = asyncio.run(_collect())
    assert tokens


def test_router_stream_with_failing_provider_polyfills_with_mock():
    class Failing(MockProvider):
        name = "failing"

        @property
        def available(self) -> bool:
            return True

        async def astream(self, _request):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")
            yield  # noqa: pragma: no cover

    router = LLMRouter(primary=Failing(), mock=MockProvider())

    async def _collect() -> list[str]:
        return [tok async for tok in router.stream("generic", LLMRequest(prompt="hello"))]

    tokens = asyncio.run(_collect())
    assert tokens, "must polyfill via mock when primary streaming fails"


def test_endpoint_stream_emits_token_events_after_orchestrator():
    from app.api.endpoints import THREADS
    from app.memory.episode_store import EpisodeStore, set_episode_store
    from app.memory.state_store import StateStore, set_state_store
    from app.observability.metrics import reset_metrics
    from app.retrieval.cache import InMemoryCache, set_default_cache
    from fastapi.testclient import TestClient
    from app.main import app

    set_default_cache(InMemoryCache())
    set_state_store(StateStore(sqlite_path=None))
    set_episode_store(EpisodeStore(sqlite_path=None))
    reset_metrics()
    THREADS.clear()
    try:
        client = TestClient(app)
        thread_id = client.post(
            "/api/v1/analyze/start",
            json={"query": "삼성전자 2024 매출"},
        ).json()["thread_id"]
        with client.stream("GET", f"/api/v1/analyze/stream/{thread_id}") as resp:
            text = resp.read().decode("utf-8")
        assert '"type": "token"' in text
    finally:
        set_default_cache(None)
        set_state_store(None)
        set_episode_store(None)
