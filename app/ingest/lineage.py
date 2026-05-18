"""Lineage 메타 — Sprint 7 (Pillar 5).

각 Qdrant point / Neo4j node 적재 시 ``ingested_at`` / ``ingest_version`` /
``source_url`` 같은 lineage 메타를 강제 부착한다. 적재 후 사용자/감사자가
"이 데이터는 언제·어떤 파이프라인이·어디서" 가져왔는지 추적할 수 있다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

INGEST_VERSION_DEFAULT = "0.7.0"


def current_ingest_version() -> str:
    return os.getenv("INGEST_VERSION") or INGEST_VERSION_DEFAULT


@dataclass
class LineageMeta:
    source: str
    source_url: str | None = None
    ingest_version: str = field(default_factory=current_ingest_version)
    ingested_at: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "lineage": {
                "source": self.source,
                "source_url": self.source_url,
                "ingest_version": self.ingest_version,
                "ingested_at": self.ingested_at,
                **self.extra,
            }
        }


def attach_lineage(payload: dict[str, Any], meta: LineageMeta) -> dict[str, Any]:
    """payload 에 lineage 메타를 머지(in-place + 반환)."""
    out = dict(payload or {})
    lineage = meta.to_payload()["lineage"]
    out.setdefault("ingested_at", lineage["ingested_at"])
    out.setdefault("ingest_version", lineage["ingest_version"])
    out.setdefault("source", lineage["source"])
    if lineage.get("source_url") and "source_url" not in out:
        out["source_url"] = lineage["source_url"]
    out["lineage"] = lineage
    return out


__all__ = ["LineageMeta", "attach_lineage", "current_ingest_version", "INGEST_VERSION_DEFAULT"]
