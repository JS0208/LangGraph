"""의존성 0 의 in-memory metrics — Sprint 5.

Prometheus exposition (text format) 도 함께 제공한다 (`prometheus_text()`).
Sprint 6 에서 prometheus_client 의존성 도입 시, registry 인터페이스만 교체하고
호출 측은 그대로 유지된다.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any


_LABEL_SEP = "|"


def _label_key(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    return _LABEL_SEP.join(f"{k}={labels[k]}" for k in sorted(labels))


@dataclass
class _Counter:
    name: str
    description: str = ""
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class _Histogram:
    name: str
    buckets_le: list[float]
    description: str = ""
    counts: dict[str, list[int]] = field(default_factory=dict)
    sums: dict[str, float] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)


class MetricsRegistry:
    DEFAULT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

    def __init__(self) -> None:
        self._counters: dict[str, _Counter] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._lock = threading.Lock()

    def counter_inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            counter = self._counters.setdefault(name, _Counter(name=name))
            key = _label_key(labels)
            counter.values[key] = counter.values.get(key, 0.0) + float(value)

    def histogram_observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        bucket_tuple = buckets or self.DEFAULT_BUCKETS
        with self._lock:
            hist = self._histograms.get(name)
            if hist is None:
                hist = _Histogram(name=name, buckets_le=list(bucket_tuple))
                self._histograms[name] = hist
            key = _label_key(labels)
            counts = hist.counts.setdefault(key, [0] * len(hist.buckets_le))
            for idx, le in enumerate(hist.buckets_le):
                if value <= le:
                    counts[idx] += 1
            hist.sums[key] = hist.sums.get(key, 0.0) + float(value)
            hist.totals[key] = hist.totals.get(key, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters_out: dict[str, Any] = {}
            for name, c in self._counters.items():
                counters_out[name] = dict(c.values)
            histograms_out: dict[str, Any] = {}
            for name, h in self._histograms.items():
                histograms_out[name] = {
                    "buckets_le": list(h.buckets_le),
                    "totals": dict(h.totals),
                    "sums": dict(h.sums),
                }
            return {"counters": counters_out, "histograms": histograms_out}

    def prometheus_text(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, c in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for key, value in sorted(c.values.items()):
                    label_block = self._labels_for_text(key)
                    lines.append(f"{name}{label_block} {value}")
            for name, h in sorted(self._histograms.items()):
                lines.append(f"# TYPE {name} histogram")
                for key in sorted(h.totals.keys()):
                    counts = h.counts.get(key, [0] * len(h.buckets_le))
                    label_block_base = self._labels_for_text(key)
                    cumulative = 0
                    for idx, le in enumerate(h.buckets_le):
                        cumulative += counts[idx]
                        lines.append(
                            f"{name}_bucket{self._merge_labels(label_block_base, ('le', _format_le(le)))} {cumulative}"
                        )
                    lines.append(
                        f"{name}_bucket{self._merge_labels(label_block_base, ('le', '+Inf'))} {h.totals[key]}"
                    )
                    lines.append(f"{name}_count{label_block_base} {h.totals[key]}")
                    lines.append(f"{name}_sum{label_block_base} {h.sums.get(key, 0.0)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _labels_for_text(key: str) -> str:
        if not key:
            return ""
        parts = []
        for token in key.split(_LABEL_SEP):
            if not token:
                continue
            k, _, v = token.partition("=")
            parts.append(f'{k}="{v}"')
        return "{" + ",".join(parts) + "}" if parts else ""

    @staticmethod
    def _merge_labels(label_block: str, extra: tuple[str, str]) -> str:
        ek, ev = extra
        if not label_block:
            return f'{{{ek}="{ev}"}}'
        # label_block is "{a=b,c=d}". 안전하게 끝에 추가.
        inner = label_block.strip("{}")
        if inner:
            return "{" + inner + f',{ek}="{ev}"' + "}"
        return f'{{{ek}="{ev}"}}'

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


def _format_le(value: float) -> str:
    if math.isinf(value):
        return "+Inf"
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


_registry = MetricsRegistry()


def metrics_registry() -> MetricsRegistry:
    return _registry


def counter_inc(name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
    _registry.counter_inc(name, value, labels)


def histogram_observe(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> None:
    _registry.histogram_observe(name, value, labels, buckets)


def metrics_snapshot() -> dict[str, Any]:
    return _registry.snapshot()


def reset_metrics() -> None:
    _registry.reset()


__all__ = [
    "MetricsRegistry",
    "counter_inc",
    "histogram_observe",
    "metrics_registry",
    "metrics_snapshot",
    "reset_metrics",
]
