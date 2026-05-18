"""Sparse retrieval — Sprint 7 (Pillar 1 보강).

Qdrant `sparse vectors` 또는 별도 BM25 사이드카 도입 전, **의존성 0** 으로
BM25-Lite 토큰 매칭 점수를 제공한다. 한국어 문자열은 음절 단위 + 공백
어절 토큰을 함께 사용해 회수율을 끌어올린다.

설계 원칙
- in-process index. 호출 측이 corpus 를 한 번 build 하면 score(query) 호출이 O(N).
- score 는 (term_overlap × idf-style 가중) — 표준 BM25 의 단순화 버전.
- 외부 패키지(`rank_bm25`) 가 가용하면 자동 사용, 미가용 시 자체 구현.
- ``sparse_score(query, corpus)`` 는 항상 0~1 정규화 (downstream rerank 와 호환).
"""

from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence


_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")


def tokenize(text: str) -> list[str]:
    """공백 어절 + 한글 음절 bigram 토큰 (BM25 회수율 보강)."""
    if not text:
        return []
    base = [t.lower() for t in _TOKEN_RE.findall(text)]
    bigrams: list[str] = []
    for tok in base:
        if any("가" <= ch <= "힣" for ch in tok) and len(tok) >= 2:
            for i in range(len(tok) - 1):
                bigrams.append(tok[i : i + 2])
    return base + bigrams


@dataclass
class _Document:
    text: str
    tokens: list[str] = field(default_factory=list)
    length: int = 0


class BM25Lite:
    """단일 프로세스 BM25-Lite — 의존성 0.

    공식: score = Σ idf(t) × ((tf × (k1+1)) / (tf + k1 × (1 - b + b × |d| / avgdl)))
    - k1=1.5, b=0.75 기본값.
    """

    def __init__(self, corpus: Iterable[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._docs: list[_Document] = []
        df: dict[str, int] = {}
        total_len = 0
        for text in corpus:
            tokens = tokenize(text)
            doc = _Document(text=text, tokens=tokens, length=len(tokens))
            self._docs.append(doc)
            total_len += doc.length
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1
        self._N = max(1, len(self._docs))
        self._avgdl = (total_len / self._N) if self._N else 0.0
        self._idf: dict[str, float] = {
            term: math.log(1 + (self._N - cnt + 0.5) / (cnt + 0.5))
            for term, cnt in df.items()
        }

    def score(self, query: str) -> list[float]:
        if not self._docs:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return [0.0] * len(self._docs)
        scores: list[float] = []
        for doc in self._docs:
            score = 0.0
            tf_cache: dict[str, int] = {}
            for tok in doc.tokens:
                tf_cache[tok] = tf_cache.get(tok, 0) + 1
            for q in q_tokens:
                if q not in self._idf:
                    continue
                tf = tf_cache.get(q, 0)
                if tf == 0:
                    continue
                denom = tf + self._k1 * (1 - self._b + self._b * (doc.length / max(self._avgdl, 1.0)))
                score += self._idf[q] * ((tf * (self._k1 + 1)) / denom)
            scores.append(score)
        return scores

    @property
    def size(self) -> int:
        return self._N


def normalize(scores: Sequence[float]) -> list[float]:
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    span = hi - lo
    if span <= 0:
        return [0.0 for _ in scores]
    return [(s - lo) / span for s in scores]


def sparse_score(query: str, corpus: Sequence[str]) -> list[float]:
    """질의-corpus 의 정규화된 sparse 점수.

    선택적: ``rank_bm25`` 가 가용하면 BM25Okapi 사용. 미가용 시 BM25Lite.
    """
    if importlib.util.find_spec("rank_bm25") is not None:
        try:
            from rank_bm25 import BM25Okapi  # type: ignore

            tokenized = [tokenize(t) for t in corpus]
            bm25 = BM25Okapi(tokenized)
            raw = bm25.get_scores(tokenize(query))
            return normalize(list(raw))
        except Exception:  # noqa: BLE001
            pass
    bm25 = BM25Lite(corpus)
    return normalize(bm25.score(query))


__all__ = ["BM25Lite", "tokenize", "sparse_score", "normalize"]
