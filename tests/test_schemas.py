from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    STATE_SCHEMA_VERSION,
    CriticReport,
    Evidence,
    FinanceMetrics,
    QueryPlan,
    RiskPoint,
    SubQuery,
)


def test_state_schema_version_is_semver_like():
    parts = STATE_SCHEMA_VERSION.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_evidence_requires_nonempty_id():
    with pytest.raises(ValidationError):
        Evidence(evidence_id="")
    e = Evidence(evidence_id="qd:abc", source_type="DISCLOSURE")
    assert e.source_type == "DISCLOSURE"
    assert e.metadata == {}


def test_finance_metrics_from_legacy_handles_missing_fields():
    legacy = {"debt_ratio": "180.5", "insight": "부채비율 상승", "source": "real_llm"}
    fm = FinanceMetrics.from_legacy(legacy)
    assert fm.debt_ratio == pytest.approx(180.5)
    assert fm.insight == "부채비율 상승"
    assert fm.source == "real_llm"


def test_finance_metrics_from_legacy_normalizes_invalid_source():
    fm = FinanceMetrics.from_legacy({"debt_ratio": None, "source": "weird"})
    assert fm.source == "fallback"
    assert fm.debt_ratio == 0.0


def test_risk_point_from_string():
    rp = RiskPoint.from_string("규제 조사 진행")
    assert rp.text == "규제 조사 진행"
    assert rp.severity == "unknown"


def test_critic_report_score_bounds():
    with pytest.raises(ValidationError):
        CriticReport(disagreement_score=1.5)
    cr = CriticReport(disagreement_score=0.3, request_re_retrieval=True)
    assert 0 <= cr.disagreement_score <= 1


def test_query_plan_default_intent():
    qp = QueryPlan()
    assert qp.overall_intent == "facts"
    assert qp.sub_queries == []


def test_sub_query_intent_literal():
    sq = SubQuery(text="카카오 부채비율", intent="facts")
    assert sq.intent == "facts"
