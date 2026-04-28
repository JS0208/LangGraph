from __future__ import annotations

from pathlib import Path

from app.memory.episode_store import EpisodeStore
from app.memory.state_store import StateStore


def test_state_store_save_and_snapshot(tmp_path: Path):
    store = StateStore(sqlite_path=tmp_path / "state.sqlite")
    store.save("t1", {"user_query": "삼성전자", "evidence": [{"evidence_id": "qd:1"}]})
    snap = store.snapshot("t1")
    assert snap is not None
    assert snap["user_query"] == "삼성전자"
    assert snap["evidence"][0]["evidence_id"] == "qd:1"


def test_state_store_persists_across_instances(tmp_path: Path):
    db = tmp_path / "p.sqlite"
    StateStore(sqlite_path=db).save("tx", {"a": 1, "b": [1, 2]})
    snap = StateStore(sqlite_path=db).snapshot("tx")
    assert snap == {"a": 1, "b": [1, 2]}


def test_state_store_interrupt_lifecycle(tmp_path: Path):
    store = StateStore(sqlite_path=tmp_path / "i.sqlite")
    assert store.is_cancel_requested("t") is False
    store.request_cancel("t", reason="user")
    assert store.is_cancel_requested("t") is True
    consumed, reason = store.consume_cancel("t")
    assert consumed is True
    assert reason == "user"
    assert store.is_cancel_requested("t") is False


def test_state_store_in_memory_only(tmp_path: Path):
    store = StateStore(sqlite_path=None)
    store.save("t", {"k": "v"})
    assert store.snapshot("t") == {"k": "v"}


def test_episode_store_record_and_latest(tmp_path: Path):
    store = EpisodeStore(sqlite_path=tmp_path / "ep.sqlite")
    store.record(
        thread_id="t1",
        query="카카오 2024 실적",
        final_state={
            "intent": "facts",
            "consensus_reached": True,
            "disagreement_score": 0.1,
            "evidence": [{"evidence_id": "qd:1"}, {"evidence_id": "graph:카카오"}],
            "finance_metrics": {"debt_ratio": 80},
            "risk_points": ["규제"],
        },
        duration_ms=1234.0,
    )
    latest = store.latest()
    assert len(latest) == 1
    e = latest[0]
    assert e["thread_id"] == "t1"
    assert e["consensus_reached"] is True
    assert e["evidence_ids"] == ["qd:1", "graph:카카오"]
    assert e["risk_points"] == ["규제"]


def test_episode_store_in_memory_cap():
    store = EpisodeStore(sqlite_path=None)
    for i in range(300):
        store.record(thread_id=f"t{i}", query=f"q{i}", final_state={})
    assert store.count() <= 256
