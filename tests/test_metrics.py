from __future__ import annotations

import math

from app.observability.metrics import (
    MetricsRegistry,
    counter_inc,
    histogram_observe,
    metrics_snapshot,
    reset_metrics,
)


def test_counter_increment_and_labels():
    reset_metrics()
    counter_inc("graphrag_test_counter", 1.0, {"node": "finance"})
    counter_inc("graphrag_test_counter", 2.0, {"node": "finance"})
    counter_inc("graphrag_test_counter", 1.0, {"node": "risk"})
    snap = metrics_snapshot()
    assert snap["counters"]["graphrag_test_counter"]["node=finance"] == 3.0
    assert snap["counters"]["graphrag_test_counter"]["node=risk"] == 1.0


def test_histogram_observe_buckets():
    reg = MetricsRegistry()
    reg.histogram_observe("h", 0.05)
    reg.histogram_observe("h", 0.5)
    reg.histogram_observe("h", 12.0)
    snap = reg.snapshot()
    assert snap["histograms"]["h"]["totals"][""] == 3
    assert math.isclose(snap["histograms"]["h"]["sums"][""], 12.55, rel_tol=1e-6)


def test_prometheus_text_format_smoke():
    reg = MetricsRegistry()
    reg.counter_inc("graphrag_test_total", 5.0)
    reg.histogram_observe("graphrag_test_latency_ms", 250.0, {"path": "/x"}, buckets=(100.0, 500.0, 1000.0))
    text = reg.prometheus_text()
    assert "graphrag_test_total" in text
    assert "graphrag_test_latency_ms_bucket" in text
    assert 'le="+Inf"' in text


def test_reset_clears_state():
    counter_inc("once", 1.0)
    reset_metrics()
    assert metrics_snapshot()["counters"] == {}
