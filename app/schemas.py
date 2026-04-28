"""Pydantic v2 모델 모음 — Sprint 1 (Foundations).

핵심 원칙
- 모든 외부 LLM 출력은 이 스키마들로 1차 검증된다.
- 모든 결론은 evidence_ids 를 가질 수 있도록 필드를 보유한다 (Sprint 3에서 강제화).
- 기존 dict 기반 호출과의 하위호환을 위해, 각 모델은 ``model_dump()`` 또는
  ``from_legacy()`` 어댑터를 제공한다.

이 모듈은 import 만으로는 외부 사이드이펙트를 일으키지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STATE_SCHEMA_VERSION = "1.1.0"

EvidenceSourceType = Literal[
    "FINANCIAL_REPORT",
    "DISCLOSURE",
    "DART_REPORT",
    "GRAPH",
    "NEWS",
    "SEED",
    "USER_PROVIDED",
]

QueryIntent = Literal["facts", "relation", "trend", "risk", "out_of_scope"]


class _BaseModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class Evidence(_BaseModel):
    """검색·추론 단계에서 인용 가능한 단일 근거.

    `evidence_id` 는 chunk_id (Qdrant) 또는 ``graph:<node_id>`` 형식의
    Neo4j 노드 식별자, 또는 ``seed:<index>`` (fallback) 셋 중 하나다.
    """

    evidence_id: str
    source_type: EvidenceSourceType = "DART_REPORT"
    company_name: str | None = None
    year: int | None = None
    text_preview: str = ""
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_id")
    @classmethod
    def _evidence_id_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("evidence_id must be non-empty")
        return v


class FinanceMetrics(_BaseModel):
    """`finance_analyst_node` 가 산출하는 정량 분석 결과."""

    debt_ratio: float = 0.0
    revenue: float | None = None
    operating_profit: float | None = None
    insight: str = ""
    has_sufficient_data: bool = False
    data_quality: str = "ok"
    source: Literal["fallback", "real_llm", "parse_error", "mock"] = "fallback"
    evidence_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_legacy(cls, payload: dict[str, Any]) -> "FinanceMetrics":
        """기존 dict 출력(``app/agents/llm_structured.py``)을 안전하게 흡수."""
        debt = payload.get("debt_ratio")
        try:
            debt_value = float(debt) if debt is not None else 0.0
        except (TypeError, ValueError):
            debt_value = 0.0
        return cls(
            debt_ratio=debt_value,
            insight=str(payload.get("insight", "")),
            has_sufficient_data=bool(payload.get("has_sufficient_data", False)),
            data_quality=str(payload.get("data_quality", "ok")),
            source=payload.get("source", "fallback") if payload.get("source") in {"fallback", "real_llm", "parse_error", "mock"} else "fallback",
            evidence_ids=list(payload.get("evidence_ids", []) or []),
        )


class RiskPoint(_BaseModel):
    """리스크 항목 (구조화). 자유 문자열만 다루던 기존 출력의 상위 호환."""

    text: str
    event_type: str | None = None
    severity: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_string(cls, raw: str) -> "RiskPoint":
        return cls(text=raw)


class CriticReport(_BaseModel):
    """비판자(Critic) 노드의 판정 — Sprint 3에서 사용 시작."""

    disagreement_score: float = Field(ge=0.0, le=1.0, default=0.0)
    missing_citations: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    request_re_retrieval: bool = False
    notes: str = ""


class SubQuery(_BaseModel):
    """질의 분해(Decomposition) 결과의 단위."""

    text: str
    intent: QueryIntent = "facts"
    target_company: str | None = None
    target_year: int | None = None
    weight: float = 1.0


class QueryPlan(_BaseModel):
    """Planner 노드 산출물 — Sprint 2에서 채워진다."""

    sub_queries: list[SubQuery] = Field(default_factory=list)
    overall_intent: QueryIntent = "facts"
    needs_graph: bool = True
    needs_vector: bool = True


class LLMUsage(_BaseModel):
    """LLM 호출 메타 (OTel span attribute로 동시 기록 예정)."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False


class TraceMeta(_BaseModel):
    """요청 단위 운영 메타."""

    trace_id: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cost_usd: float = 0.0


__all__ = [
    "STATE_SCHEMA_VERSION",
    "Evidence",
    "FinanceMetrics",
    "RiskPoint",
    "CriticReport",
    "SubQuery",
    "QueryPlan",
    "LLMUsage",
    "TraceMeta",
    "EvidenceSourceType",
    "QueryIntent",
]
