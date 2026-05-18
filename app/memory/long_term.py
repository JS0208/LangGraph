"""Long-term Vector Memory — Sprint 7 (Pillar 3).

목적
- ``user_memory_{user_id}`` 컨셉 — 사용자/조직 단위 장기 메모리.
- Qdrant 등 외부 벡터 DB가 가용하면 그쪽으로 슬롯 인할 수 있도록 인터페이스 분리.
- 의존성 0: 기본은 sqlite + token Jaccard 유사도 검색.

스키마 (sqlite ``user_memories``)
- user_id TEXT, key TEXT, summary TEXT, tags TEXT(JSON), created_at REAL
- (user_id, key) PRIMARY KEY

API
- ``remember(user_id, summary, tags=...)`` → key 반환
- ``recall(user_id, query, k=3)`` → 점수 순 [{summary, score, ...}]
- ``forget(user_id, key)`` / ``clear(user_id=None)``
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.retrieval.sparse import tokenize


def _key_for(user_id: str, summary: str) -> str:
    h = hashlib.sha1(f"{user_id}|{summary}".encode("utf-8")).hexdigest()
    return f"mem:{h[:16]}"


def _jaccard(a: str, b: str) -> float:
    sa = set(tokenize(a))
    sb = set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class LongTermMemory:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS user_memories (
        user_id TEXT NOT NULL,
        key TEXT NOT NULL,
        summary TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, key)
    );
    CREATE INDEX IF NOT EXISTS idx_mem_user_created ON user_memories(user_id, created_at DESC);
    """

    def __init__(self, sqlite_path: str | Path | None = ".cache/long_term_memory.sqlite") -> None:
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

    def remember(
        self,
        user_id: str,
        summary: str,
        *,
        tags: list[str] | None = None,
    ) -> str:
        if not user_id or not summary:
            return ""
        key = _key_for(user_id, summary)
        rec = {
            "user_id": user_id,
            "key": key,
            "summary": summary,
            "tags": list(tags or []),
            "created_at": time.time(),
        }
        with self._lock:
            self._mem.append(rec)
            if len(self._mem) > 1024:
                self._mem = self._mem[-1024:]
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO user_memories(user_id, key, summary, tags, created_at) VALUES (?,?,?,?,?);",
                        (user_id, key, summary, json.dumps(rec["tags"], ensure_ascii=False), rec["created_at"]),
                    )
            except sqlite3.OperationalError:
                pass
        return key

    def recall(self, user_id: str, query: str, *, k: int = 3) -> list[dict[str, Any]]:
        if not user_id or not query:
            return []
        candidates: list[dict[str, Any]] = []
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT key, summary, tags, created_at FROM user_memories WHERE user_id=? ORDER BY created_at DESC LIMIT 200;",
                        (user_id,),
                    ).fetchall()
                for row in rows:
                    candidates.append(
                        {
                            "key": row[0],
                            "summary": row[1],
                            "tags": json.loads(row[2] or "[]"),
                            "created_at": float(row[3]),
                        }
                    )
            except sqlite3.OperationalError:
                pass
        if not candidates:
            with self._lock:
                candidates = [c for c in reversed(self._mem) if c["user_id"] == user_id][:200]
                candidates = [
                    {
                        "key": c["key"],
                        "summary": c["summary"],
                        "tags": list(c["tags"]),
                        "created_at": c["created_at"],
                    }
                    for c in candidates
                ]

        scored = sorted(
            (
                {**c, "score": _jaccard(query, c["summary"])}
                for c in candidates
            ),
            key=lambda c: c["score"],
            reverse=True,
        )
        return [c for c in scored if c["score"] > 0][: max(1, k)]

    def forget(self, user_id: str, key: str) -> None:
        with self._lock:
            self._mem = [c for c in self._mem if not (c["user_id"] == user_id and c["key"] == key)]
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM user_memories WHERE user_id=? AND key=?;",
                        (user_id, key),
                    )
            except sqlite3.OperationalError:
                pass

    def clear(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._mem.clear()
            else:
                self._mem = [c for c in self._mem if c["user_id"] != user_id]
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    if user_id is None:
                        conn.execute("DELETE FROM user_memories;")
                    else:
                        conn.execute("DELETE FROM user_memories WHERE user_id=?;", (user_id,))
            except sqlite3.OperationalError:
                pass


_default: LongTermMemory | None = None


def get_long_term_memory() -> LongTermMemory:
    global _default
    if _default is None:
        _default = LongTermMemory()
    return _default


def set_long_term_memory(mem: LongTermMemory | None) -> None:
    global _default
    _default = mem


__all__ = [
    "LongTermMemory",
    "get_long_term_memory",
    "set_long_term_memory",
]
