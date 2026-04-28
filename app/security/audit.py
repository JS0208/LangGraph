"""감사 로그 — append-only.

저장 방식: in-memory + sqlite. 운영 환경에서는 Sprint 6+ 에서 외부 SIEM/CloudWatch
로 forwarding 한다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class AuditLog:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        actor TEXT,
        action TEXT NOT NULL,
        resource TEXT,
        result TEXT,
        meta TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts DESC);
    """

    def __init__(self, sqlite_path: str | Path | None = ".cache/audit.sqlite") -> None:
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

    def append(
        self,
        action: str,
        *,
        actor: str | None = None,
        resource: str | None = None,
        result: str | None = "ok",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "ts": time.time(),
            "actor": actor,
            "action": action,
            "resource": resource,
            "result": result,
            "meta": meta or {},
        }
        with self._lock:
            self._mem.append(event)
            if len(self._mem) > 1024:
                self._mem = self._mem[-1024:]
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO audit_events(ts, actor, action, resource, result, meta) VALUES (?,?,?,?,?,?);",
                        (
                            event["ts"],
                            event["actor"],
                            event["action"],
                            event["resource"],
                            event["result"],
                            json.dumps(event["meta"], ensure_ascii=False, default=str),
                        ),
                    )
            except sqlite3.OperationalError:
                pass
        return event

    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._mem))[:limit]

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()
        if self._sqlite_path is not None:
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM audit_events;")
            except sqlite3.OperationalError:
                pass


_default: AuditLog | None = None


def get_audit_log() -> AuditLog:
    global _default
    if _default is None:
        _default = AuditLog()
    return _default


def set_audit_log(log: AuditLog | None) -> None:
    global _default
    _default = log


def audit_event(
    action: str,
    *,
    actor: str | None = None,
    resource: str | None = None,
    result: str | None = "ok",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_audit_log().append(
        action, actor=actor, resource=resource, result=result, meta=meta
    )


__all__ = ["AuditLog", "audit_event", "get_audit_log", "set_audit_log"]
