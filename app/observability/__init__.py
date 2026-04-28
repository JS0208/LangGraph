"""Observability — Sprint 5.

- ``logging``: structlog 기반 JSON 로깅 (라이브러리 미설치 시 stdlib 로 회귀).
- ``metrics``: 의존성 0 의 in-memory 카운터/히스토그램.
  Sprint 6 에서 prometheus_client 로 wire-compatible 하게 교체된다.
"""

from app.observability.metrics import (
    counter_inc,
    histogram_observe,
    metrics_registry,
    metrics_snapshot,
    reset_metrics,
)

__all__ = [
    "counter_inc",
    "histogram_observe",
    "metrics_registry",
    "metrics_snapshot",
    "reset_metrics",
]
