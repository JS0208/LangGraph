"""Reranker with Cross-Encoder anti-antonym support."""
from __future__ import annotations

import importlib.util
import logging
import os
import re
from typing import Any, Iterable, Sequence

from app.retrieval.sparse import normalize, sparse_score, tokenize

logger = logging.getLogger(__name__)

_CROSS_ENCODER_MODEL = os.getenv(
    "CROSS_ENCODER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)

_TECHNICAL_PATTERN = re.compile(
    r"[A-Z]{2,}|[_\.]|\bAPI\b|\bSQL\b|\bIPO\b|\bROE\b|\bROA\b|\bEBITDA\b"
    r"|\bPER\b|\bPBR\b|\bEPS\b"
)
_CONCEPTUAL_PATTERN = re.compile(r"\uc774\ub780|\uac1c\ub150|\ubc29\ubc95|\uc6d0\ub9ac|\uc774\uc720|\uc758\ubbf8|\uc804\ub9dd|\ube44\uad50")


def _get_cross_encoder():
    if importlib.util.find_spec("sentence_transformers") is None:
        return None
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder(_CROSS_ENCODER_MODEL)
    except Exception as exc:
        logger.debug("CrossEncoder load failed (%s) -- using heuristic reranker", exc)
        return None


_cross_encoder_instance = None
_cross_encoder_loaded = False


def _load_cross_encoder():
    global _cross_encoder_instance, _cross_encoder_loaded
    if not _cross_encoder_loaded:
        _cross_encoder_instance = _get_cross_encoder()
        _cross_encoder_loaded = True
    return _cross_encoder_instance


def _payload_text(hit: dict) -> str:
    parts = []
    for key in ("text_content", "summary", "company_name", "event_type", "text_preview"):
        value = hit.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _payload_richness(hit: dict) -> int:
    keys = ("quarter", "revenue", "operating_profit", "debt_ratio",
            "has_financial_data", "date", "event_type", "summary")
    return sum(1 for k in keys if hit.get(k) not in (None, "", []))


def _lexical_overlap(query_tokens: set, hit_tokens: set) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens & hit_tokens) / len(query_tokens)


def alpha_for_query(query: str, intent: str | None = None) -> float:
    """Dynamically determine dense/sparse alpha based on query content + intent."""
    if _TECHNICAL_PATTERN.search(query):
        return 0.35  # sparse boost for technical terms
    if _CONCEPTUAL_PATTERN.search(query):
        return 0.65  # dense boost for conceptual queries
    if intent in {"facts", "trend"}:
        return 0.55
    if intent in {"risk", "relation"}:
        return 0.40
    return 0.50


def alpha_for_intent(intent: str | None) -> float:
    return alpha_for_query("", intent=intent)


def hybrid_blend(
    dense_scores: Sequence[float],
    sparse_scores: Sequence[float],
    *,
    alpha: float = 0.5,
) -> list:
    n = max(len(dense_scores), len(sparse_scores))
    d = list(dense_scores) + [0.0] * (n - len(dense_scores))
    s = list(sparse_scores) + [0.0] * (n - len(sparse_scores))
    d_norm = normalize(d)
    s_norm = normalize(s)
    a = max(0.0, min(1.0, alpha))
    return [a * dx + (1 - a) * sx for dx, sx in zip(d_norm, s_norm)]


def rerank(
    query: str,
    hits: Iterable[dict],
    *,
    top_k: int = 5,
    intent: str | None = None,
    dense_score_key: str = "score",
    use_cross_encoder: bool = True,
) -> list:
    """Hybrid reranker with optional Cross-Encoder for antonym disambiguation."""
    items = list(hits)
    if not items:
        return []

    corpus = [_payload_text(it) for it in items]
    dense = [float(it.get(dense_score_key, 0.0) or 0.0) for it in items]
    sparse = sparse_score(query, corpus)

    alpha = alpha_for_query(query, intent)
    blended = hybrid_blend(dense, sparse, alpha=alpha)

    q_tokens = set(tokenize(query))
    enriched = []
    for idx, it in enumerate(items):
        h_tokens = set(tokenize(corpus[idx]))
        bonus = 0.15 * _lexical_overlap(q_tokens, h_tokens)
        bonus += 0.05 * min(1.0, _payload_richness(it) / 6.0)
        score = blended[idx] + bonus
        out = dict(it)
        out["rerank_score"] = score
        out["sparse_score"] = sparse[idx] if idx < len(sparse) else 0.0
        out["hybrid_alpha"] = alpha
        enriched.append((score, out))

    enriched.sort(key=lambda kv: kv[0], reverse=True)
    candidates = enriched[: max(top_k * 3, 20)]

    if use_cross_encoder and len(candidates) > 1:
        ce = _load_cross_encoder()
        if ce is not None:
            try:
                texts = [_payload_text(item) for _s, item in candidates]
                pairs = [(query, t) for t in texts]
                ce_scores = ce.predict(pairs)
                ce_norm = normalize(list(ce_scores))
                enriched_ce = []
                for i, (_old_score, item) in enumerate(candidates):
                    item = dict(item)
                    item["cross_encoder_score"] = float(ce_norm[i])
                    enriched_ce.append((float(ce_norm[i]), item))
                enriched_ce.sort(key=lambda kv: kv[0], reverse=True)
                return [item for _score, item in enriched_ce[:max(1, top_k)]]
            except Exception as exc:
                logger.warning("CrossEncoder reranking failed (%s) -- using heuristic", exc)

    return [item for _score, item in enriched[:max(1, top_k)]]


__all__ = ["rerank", "hybrid_blend", "alpha_for_intent", "alpha_for_query"]
