"""Sprint 7 — Ingest 보강 + Long-term Memory 단위 테스트."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.ingest import (
    LineageMeta,
    QualityVerdict,
    attach_lineage,
    bounded_gather,
    current_ingest_version,
    evaluate_company_record,
    parallel_embed,
)
from app.ingest.quality import quarantine_filter
from app.ingest.watermark import WatermarkStore
from app.memory.long_term import LongTermMemory


def test_evaluate_company_record_accepts_clean_record():
    rec = {
        "name": "삼성전자",
        "year": 2024,
        "revenue": 2_800_000,
        "operating_profit": 250_000,
        "debt_ratio": 30.0,
        "has_financial_data": True,
        "disclosures": [{"date": "2024-10", "summary": "주요 공시"}],
    }
    v = evaluate_company_record(rec)
    assert isinstance(v, QualityVerdict)
    assert v.is_acceptable
    assert v.score >= 0.5


def test_evaluate_company_record_rejects_negative_debt():
    v = evaluate_company_record({"debt_ratio": -1, "revenue": 100, "operating_profit": 1})
    assert v.decision == "reject"


def test_quarantine_filter_partitions():
    accepted, quar = quarantine_filter([
        {"revenue": 100, "operating_profit": 1, "debt_ratio": 10, "has_financial_data": True, "disclosures": ["x"]},
        {"revenue": 0, "operating_profit": 0, "debt_ratio": 0, "has_financial_data": False, "disclosures": []},
    ])
    assert len(accepted) == 1
    assert len(quar) == 1
    assert quar[0]["_quality_verdict"]["decision"] in {"quarantine", "reject"}


def test_attach_lineage_includes_ingest_version():
    meta = LineageMeta(source="DART", source_url="https://opendart.fss.or.kr/")
    out = attach_lineage({"foo": 1}, meta)
    assert out["foo"] == 1
    assert out["lineage"]["source"] == "DART"
    assert out["lineage"]["ingest_version"] == current_ingest_version()


def test_parallel_embed_preserves_order():
    async def fake_embed(text: str) -> list[float]:
        await asyncio.sleep(0.001)
        return [float(len(text))]

    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(parallel_embed(["a", "bb", "ccc"], fake_embed, concurrency=2))
    finally:
        loop.close()
    assert [v[0] for v in out] == [1.0, 2.0, 3.0]


def test_bounded_gather_runs_all():
    async def _x(i):
        return i * 2

    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(bounded_gather([_x(i) for i in range(5)], limit=2))
    finally:
        loop.close()
    assert out == [0, 2, 4, 6, 8]


def test_watermark_store_roundtrip(tmp_path: Path):
    store = WatermarkStore(tmp_path / "wm.sqlite")
    assert store.get("005930", 2024) is None
    store.set("005930", 2024, "20241231000123")
    assert store.get("005930", 2024) == "20241231000123"
    store.set("005930", 2024, "20250101000045")
    assert store.get("005930", 2024) == "20250101000045"


def test_long_term_memory_remember_and_recall(tmp_path: Path):
    mem = LongTermMemory(tmp_path / "mem.sqlite")
    mem.remember("u1", "삼성전자 2024년 매출 280조원, 영업이익 30조원", tags=["finance"])
    mem.remember("u1", "카카오 자회사 규제 리스크", tags=["risk"])
    out = mem.recall("u1", "삼성전자 매출", k=2)
    assert out and "삼성" in out[0]["summary"]
    assert out[0]["score"] > 0


def test_long_term_memory_isolated_per_user(tmp_path: Path):
    mem = LongTermMemory(tmp_path / "mem.sqlite")
    mem.remember("u1", "삼성 매출")
    mem.remember("u2", "카카오 리스크")
    assert mem.recall("u1", "카카오") == []
