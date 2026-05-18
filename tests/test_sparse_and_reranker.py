"""Sprint 7 — sparse(BM25) + reranker 단위 테스트."""

from __future__ import annotations

from app.retrieval.reranker import alpha_for_intent, hybrid_blend, rerank
from app.retrieval.sparse import BM25Lite, normalize, sparse_score, tokenize


def test_tokenize_handles_korean_bigrams():
    toks = tokenize("삼성전자 2024년 부채비율")
    # 어절 + 한글 bigram 포함
    assert "2024년" in toks or "2024" in toks
    assert any(len(t) == 2 and "가" <= t[0] <= "힣" for t in toks)


def test_bm25_lite_returns_scores_per_doc():
    corpus = [
        "삼성전자 2024년 매출",
        "SK하이닉스 부채비율 안정",
        "카카오 자회사 규제 리스크",
    ]
    bm = BM25Lite(corpus)
    scores = bm.score("삼성 매출")
    assert len(scores) == 3
    # 첫 문서가 가장 관련성이 높아야 한다.
    assert scores[0] >= max(scores[1], scores[2])


def test_sparse_score_normalizes_to_0_1():
    corpus = ["삼성전자 매출", "카카오 규제", "NAVER 영업이익"]
    s = sparse_score("삼성 매출", corpus)
    assert all(0.0 <= v <= 1.0 for v in s)
    assert s[0] >= s[1]


def test_normalize_constant_returns_zeros():
    assert normalize([1.0, 1.0, 1.0]) == [0.0, 0.0, 0.0]


def test_hybrid_blend_alpha_extremes():
    d = [1.0, 0.0]
    s = [0.0, 1.0]
    assert hybrid_blend(d, s, alpha=1.0) == [1.0, 0.0]
    assert hybrid_blend(d, s, alpha=0.0) == [0.0, 1.0]


def test_alpha_for_intent_table():
    assert alpha_for_intent("facts") > 0.5
    assert alpha_for_intent("risk") < 0.5
    assert alpha_for_intent(None) == 0.5


def test_rerank_reorders_by_query_relevance():
    hits = [
        {"text_content": "카카오 규제 리스크", "score": 0.1},
        {"text_content": "삼성전자 2024 매출", "score": 0.1},
        {"text_content": "NAVER 광고 매출", "score": 0.1},
    ]
    out = rerank("삼성 매출", hits, top_k=2, intent="facts")
    assert len(out) == 2
    # 삼성/매출 둘 다 일치하는 hit 가 1순위.
    assert "삼성" in out[0]["text_content"]
    assert "rerank_score" in out[0]
