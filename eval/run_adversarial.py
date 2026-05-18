"""Adversarial 30종 차단율 평가 — Sprint 7.

목표: ``classify_input`` 가 ``expected_class`` 로 정확히 분류한 비율 ≥ 0.9.
fallback-first: LLM/DB 호출 없이 결정론으로 끝난다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.security.guardrails import classify_input  # noqa: E402


def run(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    correct = 0
    blocked = 0
    cases: list[dict] = []
    for sc in scenarios:
        verdict = classify_input(sc["query"])
        ok = verdict.classification == sc["expected_class"]
        if verdict.classification != "safe":
            blocked += 1
        if ok:
            correct += 1
        cases.append(
            {
                "id": sc["id"],
                "expected": sc["expected_class"],
                "got": verdict.classification,
                "passed": ok,
                "reasons": list(verdict.reasons),
            }
        )
    total = len(scenarios)
    return {
        "total": total,
        "block_rate": blocked / total if total else 0.0,
        "exact_classification_rate": correct / total if total else 0.0,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=str(ROOT / "eval" / "adversarial" / "v0.json"),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.9)
    args = parser.parse_args()

    result = run(Path(args.path))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("# Adversarial Eval (v0)")
        print(f"- total: {result['total']}")
        print(f"- block_rate: {result['block_rate']:.2%}")
        print(f"- exact_classification_rate: {result['exact_classification_rate']:.2%}")
        for c in result["cases"]:
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['id']} expected={c['expected']} got={c['got']}")
    if result["exact_classification_rate"] < args.threshold:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
