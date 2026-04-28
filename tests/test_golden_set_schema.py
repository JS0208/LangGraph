from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval" / "golden_set" / "v0.json"


def test_golden_set_v0_loads_and_has_minimum_questions():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["schema_version"].startswith("1."), "schema_version 은 1.x 시리즈를 유지한다"
    scenarios = data["scenarios"]
    assert len(scenarios) >= 30, "Sprint 5 이후 골든셋은 최소 30문항이어야 한다."


def test_golden_set_required_fields():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    required = {"id", "category", "query", "must_cite"}
    for scenario in data["scenarios"]:
        missing = required - scenario.keys()
        assert not missing, f"{scenario.get('id')} 누락 필드: {missing}"


def test_golden_set_includes_core_scenarios():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    labels = {s.get("scenario_label") for s in data["scenarios"]}
    assert "A_subsidiary_risk_propagation" in labels
    assert "B_deadlock_forced_termination" in labels


def test_golden_set_categories_are_valid():
    valid = {"facts", "relation", "trend", "risk", "out_of_scope"}
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        assert scenario["category"] in valid, f"잘못된 category: {scenario}"
