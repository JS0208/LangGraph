"""검색·임베딩 캐시 — Sprint 2.

설계 원칙
- ``InMemoryCache`` 는 항상 사용 가능한 1차 캐시.
- ``SqliteCache`` 는 프로세스 재기동 후에도 유지되는 영속 캐시(파일 1개, 의존성 0).
- 둘 다 동기 인터페이스로 통일하되, 비동기 호출 측에서는 그대로 await 없이 사용 가능.
- 키는 ``(namespace, sha1(payload))`` 로 고정해 충돌을 줄인다.
- Redis 캐시는 Sprint 4 에서 동일 인터페이스로 슬롯 인.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol


def _digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


class CacheBackend(Protocol):
    def get(self, namespace: str, key: Any) -> Any | None: ...
    def set(self, namespace: str, key: Any, value: Any, ttl_s: float | None = None) -> None: ...
    def clear(self, namespace: str | None = None) -> None: ...


class InMemoryCache:
    """LRU + TTL 기반 in-process 캐시. 단일 프로세스 내에서 충분히 빠르다."""

    def __init__(self, max_entries: int = 2048, default_ttl_s: float | None = None) -> None:
        self._max = max_entries
        self._default_ttl = default_ttl_s
        self._store: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, namespace: str, key: Any) -> str:
        return f"{namespace}:{_digest(key)}"

    def get(self, namespace: str, key: Any) -> Any | None:
        full_key = self._key(namespace, key)
        with self._lock:
            entry = self._store.get(full_key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.time() > expires_at:
                self._store.pop(full_key, None)
                return None
            self._store.move_to_end(full_key)
            return value

    def set(self, namespace: str, key: Any, value: Any, ttl_s: float | None = None) -> None:
        ttl = ttl_s if ttl_s is not None else self._default_ttl
        expires_at = (time.time() + ttl) if ttl is not None else None
        full_key = self._key(namespace, key)
        with self._lock:
            self._store[full_key] = (value, expires_at)
            self._store.move_to_end(full_key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def clear(self, namespace: str | None = None) -> None:
        with self._lock:
            if namespace is None:
                self._store.clear()
                return
            prefix = f"{namespace}:"
            for key in [k for k in self._store if k.startswith(prefix)]:
                self._store.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


class SqliteCache:
    """단일 파일 기반 영속 캐시. 의존성 0(stdlib)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS cache (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        expires_at REAL,
        PRIMARY KEY (namespace, key)
    );
    """

    def __init__(self, path: str | Path = ".cache/embeddings.sqlite") -> None:
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

    def get(self, namespace: str, key: Any) -> Any | None:
        digest = _digest(key)
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE namespace=? AND key=?",
                (namespace, digest),
            ).fetchone()
            if row is None:
                return None
            value_str, expires_at = row
            if expires_at is not None and expires_at < now:
                conn.execute(
                    "DELETE FROM cache WHERE namespace=? AND key=?",
                    (namespace, digest),
                )
                return None
        return json.loads(value_str)

    def set(self, namespace: str, key: Any, value: Any, ttl_s: float | None = None) -> None:
        digest = _digest(key)
        expires_at = (time.time() + ttl_s) if ttl_s is not None else None
        payload = json.dumps(value, ensure_ascii=False, default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache(namespace, key, value, expires_at) VALUES (?,?,?,?)",
                (namespace, digest, payload, expires_at),
            )

    def clear(self, namespace: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            if namespace is None:
                conn.execute("DELETE FROM cache;")
            else:
                conn.execute("DELETE FROM cache WHERE namespace=?;", (namespace,))


_default_cache: CacheBackend | None = None


def get_default_cache() -> CacheBackend:
    """프로세스 단일 캐시. Sprint 4 에서 Redis 로 교체 가능."""
    global _default_cache
    if _default_cache is None:
        _default_cache = InMemoryCache(max_entries=4096)
    return _default_cache


def set_default_cache(cache: CacheBackend | None) -> None:
    global _default_cache
    _default_cache = cache


__all__ = [
    "CacheBackend",
    "InMemoryCache",
    "SqliteCache",
    "get_default_cache",
    "set_default_cache",
]
