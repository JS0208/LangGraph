from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 테스트는 로컬 .env 또는 셸 환경에 영향을 받지 않도록 fallback 경로를 강제한다.
for key in (
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
):
    os.environ[key] = ""
