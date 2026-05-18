"""Community Summary — Sprint 7 (Pillar 1 보강).

Microsoft GraphRAG 의 Leiden/Louvain 기반 커뮤니티 검출은 외부 의존이
필요하므로 본 모듈은 **의존성 0** 의 간이 그룹화·요약 골격만 제공한다.

설계 원칙
- Neo4j 등에서 노드 페어 리스트를 받아 union-find 로 community 분할.
- 각 community 에 대해 텍스트 chunk 의 키워드 빈도/길이 기반 요약 생성.
- 요약은 별도 collection 에 저장될 수 있도록 dict 형태로 노출.
- LLM 가용 시 ``llm_summarize_community`` 가 자동으로 LLM Router 를 호출.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from app.retrieval.sparse import tokenize

logger = logging.getLogger(__name__)


@dataclass
class Community:
    community_id: str
    members: list[str] = field(default_factory=list)
    summary: str = ""
    keywords: list[str] = field(default_factory=list)


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def detect_communities(
    nodes: Iterable[str],
    edges: Iterable[tuple[str, str]],
) -> list[Community]:
    """union-find 로 약한 연결 컴포넌트 = community 로 정의."""
    uf = _UnionFind()
    nodes = list(nodes)
    for n in nodes:
        uf.find(n)
    for a, b in edges:
        uf.find(a)
        uf.find(b)
        uf.union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        groups[uf.find(n)].append(n)

    out: list[Community] = []
    for idx, (root, members) in enumerate(sorted(groups.items())):
        out.append(
            Community(
                community_id=f"c{idx:03d}:{root[:12]}",
                members=sorted(members),
            )
        )
    return out


def heuristic_summarize(community: Community, texts: Sequence[str], *, top_k: int = 8) -> Community:
    """텍스트 빈도 기반 키워드 + 가장 정보량 많은 문장 1~2개를 요약으로 사용."""
    if not texts:
        community.summary = f"({len(community.members)} members) summary unavailable"
        return community
    counter: Counter[str] = Counter()
    for t in texts:
        for tok in tokenize(t):
            if len(tok) >= 2:
                counter[tok] += 1
    keywords = [w for w, _c in counter.most_common(top_k) if not w.isdigit()]
    longest = sorted(texts, key=len, reverse=True)[:2]
    summary = " / ".join(s.strip()[:160] for s in longest if s.strip())
    community.keywords = keywords
    community.summary = (
        f"[{', '.join(community.members[:5])}] core keywords: {', '.join(keywords[:6])}. "
        f"sample: {summary}"
    )
    return community


async def llm_summarize_community(
    community: Community,
    texts: Sequence[str],
    *,
    intent: str = "generic",
) -> Community:
    """LLM 가용 시 더 자연스러운 요약을 만들고, 실패 시 휴리스틱으로 회귀."""
    try:
        from app.config import settings
        from app.llm.providers.base import LLMRequest
        from app.llm.router import get_router
    except ImportError:
        return heuristic_summarize(community, texts)

    if not getattr(settings, "has_real_llm", False):
        return heuristic_summarize(community, texts)

    prompt = (
        "다음은 같은 커뮤니티에 속한 엔티티/문서 발췌입니다. 한국어로 2~3문장 요약하세요. "
        "고유명사·연도·이벤트 키워드를 보존하세요.\n"
        f"엔티티: {', '.join(community.members[:8])}\n"
        f"발췌: {' || '.join(t[:200] for t in texts[:8])}"
    )
    try:
        router = get_router()
        request = LLMRequest(prompt=prompt, temperature=0.2, json_mode=False)
        resp = await router.invoke(intent, request)
        community.summary = (resp.text or "").strip() or community.summary
        # keyword 는 휴리스틱 결과 함께 보존.
        heuristic_summarize(community, texts)
        return community
    except Exception as exc:  # noqa: BLE001
        logger.warning("community LLM 요약 실패: %s", exc)
        return heuristic_summarize(community, texts)


__all__ = [
    "Community",
    "detect_communities",
    "heuristic_summarize",
    "llm_summarize_community",
]
