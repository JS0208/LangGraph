"""Data Quality Gate — Sprint 7 (Pillar 5).

규칙 (`evaluate_company_record`)
- 매출=0 / 음수 부채비율 → reject
- 결측률 (revenue/operating_profit/debt_ratio 중 0인 항목 비율) > 0.5 → quarantine
- disclosures 가 0건이고 has_financial_data 가 False → quarantine
- 그 외 → accept

quarantine 큐는 호출 측이 처리한다. 본 모듈은 판정만 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

REQUIRED_FINANCIAL_KEYS = ("revenue", "operating_profit", "debt_ratio")


@dataclass(frozen=True)
class QualityVerdict:
    decision: str  # "accept" | "quarantine" | "reject"
    score: float = 1.0  # 0~1, 높을수록 좋음
    reasons: tuple[str, ...] = ()

    @property
    def is_acceptable(self) -> bool:
        return self.decision == "accept"


def _missing_ratio(record: dict[str, Any]) -> float:
    n = len(REQUIRED_FINANCIAL_KEYS)
    if n == 0:
        return 0.0
    missing = sum(1 for k in REQUIRED_FINANCIAL_KEYS if not record.get(k))
    return missing / n


def evaluate_company_record(record: dict[str, Any]) -> QualityVerdict:
    """회사 단위 적재 레코드 1개를 판정."""
    if not isinstance(record, dict):
        return QualityVerdict("reject", 0.0, ("not_a_dict",))

    reasons: list[str] = []
    score = 1.0

    debt = record.get("debt_ratio")
    if isinstance(debt, (int, float)) and debt < 0:
        return QualityVerdict("reject", 0.0, ("debt_ratio_negative",))

    revenue = record.get("revenue")
    if isinstance(revenue, (int, float)) and revenue == 0 and bool(record.get("has_financial_data")):
        return QualityVerdict("reject", 0.0, ("revenue_zero_with_financial_data",))

    missing_ratio = _missing_ratio(record)
    if missing_ratio > 0.5:
        reasons.append(f"missing_ratio={missing_ratio:.2f}")
        score -= 0.4

    if not record.get("disclosures") and not record.get("has_financial_data"):
        reasons.append("no_disclosures_no_financial")
        score -= 0.3

    flags = list(record.get("data_quality_flags", []) or [])
    if "financial_parse_failed" in flags:
        reasons.append("financial_parse_failed")
        score -= 0.3

    decision = "accept"
    if score < 0.5 or len(reasons) >= 2:
        decision = "quarantine"
    return QualityVerdict(decision=decision, score=max(0.0, score), reasons=tuple(reasons))


def quarantine_filter(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """accept / quarantine 양분."""
    accepted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for r in records:
        verdict = evaluate_company_record(r)
        target = accepted if verdict.is_acceptable else quarantined
        target.append({**r, "_quality_verdict": {"decision": verdict.decision, "score": verdict.score, "reasons": list(verdict.reasons)}})
    return accepted, quarantined


__all__ = ["QualityVerdict", "evaluate_company_record", "quarantine_filter"]
