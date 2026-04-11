from __future__ import annotations

import os

REQUIRED = [
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
]


if __name__ == "__main__":
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        print("[FAIL] Missing environment variables:")
        for key in missing:
            print(f"- {key}")
        raise SystemExit(1)
    print("[PASS] All required environment variables are present.")
