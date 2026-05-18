"""OpenTelemetry-style tracing shim — Sprint 7 (Pillar 7 보강).

목적
- ``opentelemetry`` 패키지 미설치 환경에서도 **5단계 drill-down** span 트리를
  생성·수집·내보낼 수 있도록 한다.
- 패키지가 가용하면 자동으로 OTel SDK 의 ``trace.start_as_current_span`` 으로 위임.

사용 예
```python
from app.observability.tracing import start_span

async with start_span("retrieve_context", attrs={"intent": "facts"}):
    ...
```

내보내기
- ``snapshot()`` — 메모리 누적 span 트리 (테스트·디버그용)
- ``prometheus_text()`` — span 카운트·duration histogram 노출
"""

from __future__ import annotations

import contextvars
import importlib.util
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.observability.metrics import counter_inc, histogram_observe


_HAS_OTEL = importlib.util.find_spec("opentelemetry") is not None


@dataclass
class Span:
    name: str
    span_id: str
    trace_id: str
    parent_id: str | None
    started_at: float
    ended_at: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        if self.ended_at is None:
            return 0.0
        return (self.ended_at - self.started_at) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "attributes": dict(self.attributes),
            "status": self.status,
            "error": self.error,
        }


class _TraceCollector:
    def __init__(self, max_spans: int = 2048) -> None:
        self._spans: list[Span] = []
        self._lock = threading.Lock()
        self._max = max_spans

    def add(self, span: Span) -> None:
        with self._lock:
            self._spans.append(span)
            if len(self._spans) > self._max:
                self._spans = self._spans[-self._max :]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans]

    def by_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans if s.trace_id == trace_id]

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


_collector = _TraceCollector()
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "graphrag_current_span", default=None
)


def collector() -> _TraceCollector:
    return _collector


def reset_traces() -> None:
    _collector.clear()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _ensure_trace_id() -> str:
    parent = _current_span.get()
    if parent is not None:
        return parent.trace_id
    # 외부 trace_id 컨텍스트(observability.logging) 와 가능하면 일치.
    try:
        from app.observability.logging import get_trace_id

        existing = get_trace_id()
        if existing:
            return existing[:32]
    except ImportError:
        pass
    return _new_id()


@asynccontextmanager
async def start_span(name: str, *, attrs: dict[str, Any] | None = None) -> AsyncIterator[Span]:
    """OTel-style span. opentelemetry 가 있으면 그쪽 span 도 함께 생성."""
    if _HAS_OTEL:
        try:
            from opentelemetry import trace  # type: ignore

            tracer = trace.get_tracer("graphrag")
            with tracer.start_as_current_span(name) as otel_span:
                for k, v in (attrs or {}).items():
                    try:
                        otel_span.set_attribute(k, v)  # type: ignore[arg-type]
                    except Exception:  # noqa: BLE001
                        pass
                async with _local_span(name, attrs) as span:
                    yield span
                return
        except Exception:  # noqa: BLE001
            pass
    async with _local_span(name, attrs) as span:
        yield span


@asynccontextmanager
async def _local_span(name: str, attrs: dict[str, Any] | None = None) -> AsyncIterator[Span]:
    parent = _current_span.get()
    span = Span(
        name=name,
        span_id=_new_id(),
        trace_id=_ensure_trace_id(),
        parent_id=parent.span_id if parent else None,
        started_at=time.time(),
        attributes=dict(attrs or {}),
    )
    token = _current_span.set(span)
    counter_inc("otel_span_started_total", 1.0, {"name": name})
    try:
        yield span
        span.status = "ok"
    except Exception as exc:  # noqa: BLE001
        span.status = "error"
        span.error = str(exc)
        counter_inc("otel_span_errors_total", 1.0, {"name": name})
        raise
    finally:
        span.ended_at = time.time()
        _current_span.reset(token)
        _collector.add(span)
        histogram_observe(
            "otel_span_duration_ms",
            span.duration_ms,
            {"name": name, "status": span.status},
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
        )


def current_span() -> Span | None:
    return _current_span.get()


__all__ = [
    "Span",
    "start_span",
    "collector",
    "reset_traces",
    "current_span",
]
