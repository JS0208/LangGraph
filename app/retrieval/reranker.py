"""Reranker — Sprint 7 (Pillar 1 보강).

목적
- dense + sparse 결과를 섞고(α 가중), 휴리스틱 reranker 로 K=20 → 5 로 축약.
- 외부 BGE/Cohere 가용 시 자동으로 슬롯 인되도록 인터페이스를 단순화.

설계 원칙
- 의존성 0 — 기본 reranker 는 lexical overlap + payload richness 가중.
- ``rerank(query, hits)`` 는 동일 hit 객체 리스트(점수만 갱신/정렬)를 반환.
- α(dense vs sparse) 가중치는 query intent 별로 동적 조정 가능 (planner 가 힌트 제공).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from app.retrieval.sparse import normalize, sparse_score, tokenize


def _payload_text(hit: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("text_content", "summary", "company_name", "event_type", "text_preview"):
        value = hit.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _payload_richness(hit: dict[str, Any]) -> int:
    keys = (
        "quarter",
        "revenue",
        "operating_profit",
        "debt_ratio",
        "has_financial_data",
        "date",
        "event_type",
        "summary",
    )
    return sum(1 for k in keys if hit.get(k) not in (None, "", []))


def _lexical_overlap(query_tokens: set[str], hit_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens & hit_tokens) / len(query_tokens)


def hybrid_blend(
    dense_scores: Sequence[float],
    sparse_scores: Sequence[float],
    *,
    alpha: float = 0.5,
) -> list[float]:
    """dense·sparse 점수 가중 합산. alpha 가 클수록 dense 우선.

    길이가 다르면 짧은 쪽을 0 으로 패딩.
    """
    n = max(len(dense_scores), len(sparse_scores))
    d = list(dense_scores) + [0.0] * (n - len(dense_scores))
    s = list(sparse_scores) + [0.0] * (n - len(sparse_scores))
    d_norm = normalize(d)
    s_norm = normalize(s)
    a = max(0.0, min(1.0, alpha))
    return [a * dx + (1 - a) * sx for dx, sx in zip(d_norm, s_norm)]


def alpha_for_intent(intent: str | None) -> float:
    """intent 별 dense/sparse 가중 — 휴리스틱."""
    if intent in {"facts", "trend"}:
        return 0.55  # 정량 위주 — dense 약간 우세
    if intent in {"risk", "relation"}:
        return 0.4  # 키워드 매칭이 중요 — sparse 가중
    return 0.5


def rerank(
    query: str,
    hits: Iterable[dict[str, Any]],
    *,
    top_k: int = 5,
    intent: str | None = None,
    dense_score_key: str = "score",
) -> list[dict[str, Any]]:
    """휴리스틱 reranker.

    1. dense 점수(없으면 0) + sparse(BM25-Lite) 가중 합.
    2. lexical overlap 보너스, payload richness 보너스.
    3. 상위 ``top_k`` 만 반환. 각 hit 의 ``rerank_score`` 필드에 결과 점수 기록.
    """
    items = list(hits)
    if not items:
        return []

    corpus = [_payload_text(it) for it in items]
    dense = [float(it.get(dense_score_key, 0.0) or 0.0) for it in items]
    sparse = sparse_score(query, corpus)
    blended = hybrid_blend(dense, sparse, alpha=alpha_for_intent(intent))

    q_tokens = set(tokenize(query))
    enriched: list[tuple[float, dict[str, Any]]] = []
    for idx, it in enumerate(items):
        h_tokens = set(tokenize(corpus[idx]))
        bonus = 0.15 * _lexical_overlap(q_tokens, h_tokens)
        bonus += 0.05 * min(1.0, _payload_richness(it) / 6.0)
        score = blended[idx] + bonus
        out = dict(it)
        out["rerank_score"] = score
        out["sparse_score"] = sparse[idx] if idx < len(sparse) else 0.0
        enriched.append((score, out))

    enriched.sort(key=lambda kv: kv[0], reverse=True)
    return [item for _score, item in enriched[: max(1, top_k)]]


__all__ = [
    "rerank",
    "hybrid_blend",
    "alpha_for_intent",
]
