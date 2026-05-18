"""DART rcept_no 기준 워터마크 — Sprint 7 (Pillar 5).

영속화는 sqlite 한 파일. 동일 (corp_code, year) 의 마지막 처리 rcept_no 만 기억.
다음 적재 사이클은 워터마크보다 큰 rcept_no 만 처리한다 (incremental ingest).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class WatermarkStore:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS ingest_watermark (
        corp_code TEXT NOT NULL,
        year INTEGER NOT NULL,
        last_rcept_no TEXT NOT NULL,
        updated_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (corp_code, year)
    );
    """

    def __init__(self, path: str | Path = ".cache/ingest_watermark.sqlite") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._path), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
        finally:
            conn.close()

    def get(self, corp_code: str, year: int) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT last_rcept_no FROM ingest_watermark WHERE corp_code=? AND year=?;",
                (corp_code, int(year)),
            ).fetchone()
            return row[0] if row else None

    def set(self, corp_code: str, year: int, rcept_no: str, updated_at: float = 0.0) -> None:
        if not corp_code or not rcept_no:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ingest_watermark(corp_code, year, last_rcept_no, updated_at) VALUES (?,?,?,?);",
                (corp_code, int(year), str(rcept_no), float(updated_at)),
            )

    def all(self) -> list[tuple[str, int, str]]:
        with self._lock, self._connect() as conn:
            return [
                (r[0], int(r[1]), r[2])
                for r in conn.execute(
                    "SELECT corp_code, year, last_rcept_no FROM ingest_watermark ORDER BY corp_code, year;"
                ).fetchall()
            ]

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM ingest_watermark;")


_default_store: WatermarkStore | None = None


def get_watermark_store() -> WatermarkStore:
    global _default_store
    if _default_store is None:
        _default_store = WatermarkStore()
    return _default_store


__all__ = ["WatermarkStore", "get_watermark_store"]
