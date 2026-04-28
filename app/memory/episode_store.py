"""분석 종료 시 결과를 archive — RAGAS·회고 분석·재현용.

각 episode 는 다음을 포함한다.
- thread_id, query, intent
- finance_metrics, risk_points, evidence_ids
- consensus_reached, disagreement_score
- duration_ms, completed_at
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class EpisodeStore:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS episodes (
        thread_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        intent TEXT,
        consensus_reached INTEGER NOT NULL DEFAULT 0,
        disagreement_score REAL NOT NULL DEFAULT 0.0,
        evidence_ids TEXT NOT NULL DEFAULT '[]',
        finance_metrics TEXT NOT NULL DEFAULT '{}',
        risk_points TEXT NOT NULL DEFAULT '[]',
        duration_ms REAL NOT NULL DEFAULT 0.0,
        completed_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_episodes_completed_at ON episodes(completed_at DESC);
    """

    def __init__(self, sqlite_path: str | Path | None = ".cache/episodes.sqlite") -> None:
        self._mem: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._sqlite_path = Path(sqlite_path) if sqlite_path else None
        if self._sqlite_path is not None:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(self.SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._sqlite_path is None:
            raise RuntimeError("sqlite path is not configured")
        conn = sqlite3.connect(str(self._sqlite_path), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        thread_id: str,
        query: str,
        final_state: dict[str, Any],
        duration_ms: float = 0.0,
    ) -> None:
        if not thread_id:
            return
        evidence_ids = [
            ev.get("evidence_id")
            for ev in final_state.get("evidence", []) or []
            if isinstance(ev, dict) and ev.get("evidence_id")
        ]
        episode = {
            "thread_id": thread_id,
            "query": query,
            "intent": final_state.get("intent"),
            "consensus_reached": bool(final_state.get("consensus_reached", False)),
            "disagreement_score": float(final_state.get("disagreement_score", 0.0) or 0.0),
            "evidence_ids": evidence_ids,
            "finance_metrics": final_state.get("finance_metrics") or {},
            "risk_points": final_state.get("risk_points") or [],
            "duration_ms": duration_ms,
            "completed_at": time.time(),
        }
        with self._lock:
            self._mem.append(episode)
            if len(self._mem) > 256:
                self._mem = self._mem[-256:]
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO episodes("
                        "thread_id, query, intent, consensus_reached, disagreement_score,"
                        "evidence_ids, finance_metrics, risk_points, duration_ms, completed_at"
                        ") VALUES (?,?,?,?,?,?,?,?,?,?);",
                        (
                            episode["thread_id"],
                            episode["query"],
                            episode["intent"],
                            int(episode["consensus_reached"]),
                            episode["disagreement_score"],
                            json.dumps(episode["evidence_ids"], ensure_ascii=False),
                            json.dumps(episode["finance_metrics"], ensure_ascii=False, default=str),
                            json.dumps(episode["risk_points"], ensure_ascii=False, default=str),
                            episode["duration_ms"],
                            episode["completed_at"],
                        ),
                    )
            except sqlite3.OperationalError:
                pass

    def latest(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._mem))[:limit]

    def count(self) -> int:
        with self._lock:
            return len(self._mem)

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM episodes;")
            except sqlite3.OperationalError:
                pass


_default_store: EpisodeStore | None = None


def get_episode_store() -> EpisodeStore:
    global _default_store
    if _default_store is None:
        _default_store = EpisodeStore()
    return _default_store


def set_episode_store(store: EpisodeStore | None) -> None:
    global _default_store
    _default_store = store


__all__ = ["EpisodeStore", "get_episode_store", "set_episode_store"]
