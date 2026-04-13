from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    path: Path

    def passed(self) -> bool:
        return self.path.exists()


def main() -> None:
    checks = [
        Check("State contract", Path("app/state.py")),
        Check("Orchestration graph", Path("app/agents/graph.py")),
        Check("Routing logic", Path("app/agents/edges.py")),
        Check("Nodes", Path("app/agents/nodes.py")),
        Check("Retrieval fallback", Path("app/retrieval/query_router.py")),
        Check("Real retrieval clients", Path("app/retrieval/real_clients.py")),
        Check("LLM structured adapters", Path("app/agents/llm_structured.py")),
        Check("Runtime settings", Path("app/config.py")),
        Check("Seed data", Path("tests/seed_data/mock_dart_response.json")),
        Check("Unit tests A", Path("tests/test_router_and_nodes.py")),
        Check("Unit tests B", Path("tests/test_retrieval_and_graph.py")),
        Check("Human task split", Path("9_Human_Required_Tasks.md")),
        Check("Perfect plan", Path("11_Product_Blueprint.md")),
        Check("Progress dashboard", Path("7_Progress_Dashboard.md")),
        Check("UX/UI master plan", Path("12_UX_UI_Master_Plan.md")),
        Check("Frontend prototype", Path("frontend_prototype/index.html")),
        Check("Human integration playbook", Path("10_Real_Integration_Playbook.md")),
        Check("Environment template", Path(".env.example")),
        Check("Preflight checker", Path("scripts/preflight_check.py")),
    ]

    passed = sum(1 for c in checks if c.passed())
    total = len(checks)
    pct = round((passed / total) * 100, 1)

    print("# Project Audit")
    for c in checks:
        mark = "PASS" if c.passed() else "FAIL"
        print(f"- [{mark}] {c.name}: {c.path}")
    print(f"\nAutomation evidence completeness: {passed}/{total} ({pct}%)")


if __name__ == "__main__":
    main()
