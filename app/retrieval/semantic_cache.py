"""Semantic answer cache — Sprint 7 (Pillar 1 보강).

cosine ≥ τ (default 0.97) 조건에서 동일 질의로 간주해 이전 답변 재사용.

설계 원칙
- 의존성 0. 임베딩이 없으면 token Jaccard 유사도로 회귀 (보수적 임계).
- LLM 임베딩이 가용하면 ``set_embedder()`` 로 주입 → cosine 사용.
- 저장소: in-memory + 선택적 sqlite 영속화 (cache.SqliteCache 위에 얹음).
- 캐시 hit 시 ``cache_hit_total`` 메트릭 카운트.
"""

from __future__ import annotations

import math
import threading
from typing import Awaitable, Callable, Sequence

from app.observability.metrics import counter_inc
from app.retrieval.cache import CacheBackend, InMemoryCache
from app.retrieval.sparse import tokenize


Embedder = Callable[[str], Awaitable[Sequence[float]]]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _jaccard(a: str, b: str) -> float:
    sa = set(tokenize(a))
    sb = set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class SemanticAnswerCache:
    NAMESPACE = "semantic_answer"

    def __init__(
        self,
        *,
        backend: CacheBackend | None = None,
        threshold: float = 0.97,
        max_entries: int = 256,
        embedder: Embedder | None = None,
    ) -> None:
        self._backend = backend or InMemoryCache(max_entries=max_entries)
        self._threshold = threshold
        self._embedder = embedder
        self._index: list[tuple[str, list[float]]] = []  # (query, embedding) — embedder 가용 시
        self._keys: list[str] = []  # 저장 순서대로의 쿼리 — Jaccard fallback 용 (항상 유지)
        self._lock = threading.Lock()

    def set_embedder(self, embedder: Embedder | None) -> None:
        with self._lock:
            self._embedder = embedder

    @property
    def threshold(self) -> float:
        return self._threshold

    async def lookup(self, query: str) -> dict | None:
        if not query:
            return None
        # 1) exact match
        exact = self._backend.get(self.NAMESPACE, query)
        if exact is not None:
            counter_inc("semantic_cache_hits_total", 1.0, {"kind": "exact"})
            return exact
        # 2) embedding cosine — embedder 가 있으면.
        if self._embedder is not None:
            try:
                emb = list(await self._embedder(query))
            except Exception:  # noqa: BLE001
                emb = []
            if emb:
                with self._lock:
                    candidates = list(self._index)
                best = ("", 0.0)
                for cached_q, cached_emb in candidates:
                    sim = _cosine(emb, cached_emb)
                    if sim > best[1]:
                        best = (cached_q, sim)
                if best[1] >= self._threshold:
                    cached = self._backend.get(self.NAMESPACE, best[0])
                    if cached is not None:
                        counter_inc(
                            "semantic_cache_hits_total",
                            1.0,
                            {"kind": "cosine"},
                        )
                        return cached
        # 3) Jaccard fallback (보수적) — embedder 가 없어도 동작.
        with self._lock:
            candidates = list(self._keys)
        for q in candidates:
            if _jaccard(query, q) >= max(0.85, self._threshold - 0.1):
                cached = self._backend.get(self.NAMESPACE, q)
                if cached is not None:
                    counter_inc("semantic_cache_hits_total", 1.0, {"kind": "jaccard"})
                    return cached
        return None

    async def store(self, query: str, value: dict, ttl_s: float | None = 3600.0) -> None:
        if not query:
            return
        self._backend.set(self.NAMESPACE, query, value, ttl_s=ttl_s)
        with self._lock:
            self._keys = [k for k in self._keys if k != query]
            self._keys.append(query)
            if len(self._keys) > 1024:
                self._keys = self._keys[-1024:]
        if self._embedder is not None:
            try:
                emb = list(await self._embedder(query))
            except Exception:  # noqa: BLE001
                emb = []
            if emb:
                with self._lock:
                    # 중복 질의는 최신값으로 유지.
                    self._index = [(q, e) for q, e in self._index if q != query]
                    self._index.append((query, emb))
                    if len(self._index) > 512:
                        self._index = self._index[-512:]
        counter_inc("semantic_cache_store_total", 1.0)

    def clear(self) -> None:
        self._backend.clear(self.NAMESPACE)
        with self._lock:
            self._index.clear()
            self._keys.clear()


_default_semantic_cache: SemanticAnswerCache | None = None


def get_semantic_cache() -> SemanticAnswerCache:
    global _default_semantic_cache
    if _default_semantic_cache is None:
        _default_semantic_cache = SemanticAnswerCache()
    return _default_semantic_cache


def set_semantic_cache(cache: SemanticAnswerCache | None) -> None:
    global _default_semantic_cache
    _default_semantic_cache = cache


__all__ = [
    "SemanticAnswerCache",
    "get_semantic_cache",
    "set_semantic_cache",
]
