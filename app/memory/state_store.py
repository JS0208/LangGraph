"""Thread 단위 GraphState 스냅샷 저장소.

설계
- 동일 thread_id 의 가장 최근 상태만 보관 (덮어쓰기).
- 메모리 dict + sqlite dual: 메모리는 빠른 read/write, sqlite 는 프로세스 재기동 보장.
- ``app/memory`` 외부에서는 ``get_state_store()`` 만 사용한다.

interrupt API 가 호출되면 ``cancel()`` 로 진행 중 코루틴에 신호를 보내고,
resume API 가 호출되면 ``snapshot(thread_id)`` 로 마지막 state 를 꺼내 patch 적용 후 재진입한다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class _InterruptRegistry:
    """interrupt 요청을 thread-safe 하게 추적."""

    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._reasons: dict[str, str] = {}
        self._lock = threading.Lock()

    def request_cancel(self, thread_id: str, reason: str = "user_interrupt") -> None:
        with self._lock:
            self._flags[thread_id] = True
            self._reasons[thread_id] = reason

    def consume_cancel(self, thread_id: str) -> tuple[bool, str | None]:
        with self._lock:
            if self._flags.pop(thread_id, False):
                return True, self._reasons.pop(thread_id, None)
            return False, None

    def is_cancel_requested(self, thread_id: str) -> bool:
        with self._lock:
            return self._flags.get(thread_id, False)

    def clear(self, thread_id: str | None = None) -> None:
        with self._lock:
            if thread_id is None:
                self._flags.clear()
                self._reasons.clear()
            else:
                self._flags.pop(thread_id, None)
                self._reasons.pop(thread_id, None)


class StateStore:
    """thread_id 별 최신 GraphState 보관."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS state_snapshots (
        thread_id TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        updated_at REAL NOT NULL
    );
    """

    def __init__(self, sqlite_path: str | Path | None = ".cache/state_store.sqlite") -> None:
        self._mem: dict[str, dict[str, Any]] = {}
        self._mem_ts: dict[str, float] = {}
        self._lock = threading.Lock()
        self._interrupts = _InterruptRegistry()
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

    # --- snapshot ----------------------------------------------------------

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        if not thread_id:
            return
        # state 에는 list/dict/숫자/문자열만 포함된다고 가정 (TypedDict).
        payload = json.loads(json.dumps(state, ensure_ascii=False, default=str))
        now = time.time()
        with self._lock:
            self._mem[thread_id] = payload
            self._mem_ts[thread_id] = now
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO state_snapshots(thread_id, payload, updated_at) VALUES (?,?,?);",
                        (thread_id, json.dumps(payload, ensure_ascii=False), now),
                    )
            except sqlite3.OperationalError:
                pass

    def snapshot(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            cached = self._mem.get(thread_id)
        if cached is not None:
            return dict(cached)
        if self._sqlite_path is None:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM state_snapshots WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def updated_at(self, thread_id: str) -> float | None:
        with self._lock:
            return self._mem_ts.get(thread_id)

    # --- interrupt ---------------------------------------------------------

    def request_cancel(self, thread_id: str, reason: str = "user_interrupt") -> None:
        self._interrupts.request_cancel(thread_id, reason)

    def consume_cancel(self, thread_id: str) -> tuple[bool, str | None]:
        return self._interrupts.consume_cancel(thread_id)

    def is_cancel_requested(self, thread_id: str) -> bool:
        return self._interrupts.is_cancel_requested(thread_id)

    def clear_interrupts(self, thread_id: str | None = None) -> None:
        self._interrupts.clear(thread_id)


_default_store: StateStore | None = None


def get_state_store() -> StateStore:
    global _default_store
    if _default_store is None:
        _default_store = StateStore()
    return _default_store


def set_state_store(store: StateStore | None) -> None:
    global _default_store
    _default_store = store


__all__ = ["StateStore", "get_state_store", "set_state_store"]
