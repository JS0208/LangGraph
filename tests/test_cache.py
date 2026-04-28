from __future__ import annotations

import time
from pathlib import Path

from app.retrieval.cache import InMemoryCache, SqliteCache


def test_in_memory_cache_basic_set_get():
    cache = InMemoryCache(max_entries=4)
    cache.set("ns", "k1", {"a": 1})
    assert cache.get("ns", "k1") == {"a": 1}
    assert cache.get("ns", "missing") is None
    assert cache.get("other", "k1") is None


def test_in_memory_cache_lru_eviction():
    cache = InMemoryCache(max_entries=2)
    cache.set("ns", "a", 1)
    cache.set("ns", "b", 2)
    cache.set("ns", "c", 3)
    assert cache.get("ns", "a") is None
    assert cache.get("ns", "b") == 2
    assert cache.get("ns", "c") == 3


def test_in_memory_cache_ttl_expiry():
    cache = InMemoryCache()
    cache.set("ns", "k", "v", ttl_s=0.05)
    assert cache.get("ns", "k") == "v"
    time.sleep(0.1)
    assert cache.get("ns", "k") is None


def test_in_memory_cache_clear_namespace():
    cache = InMemoryCache()
    cache.set("a", "k1", 1)
    cache.set("b", "k2", 2)
    cache.clear("a")
    assert cache.get("a", "k1") is None
    assert cache.get("b", "k2") == 2


def test_sqlite_cache_round_trip(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    cache = SqliteCache(db)
    cache.set("ns", {"q": "카카오"}, [1, 2, 3])
    assert cache.get("ns", {"q": "카카오"}) == [1, 2, 3]
    assert cache.get("ns", {"q": "삼성전자"}) is None
    cache.clear("ns")
    assert cache.get("ns", {"q": "카카오"}) is None


def test_sqlite_cache_persists_across_instances(tmp_path: Path):
    db = tmp_path / "p.sqlite"
    SqliteCache(db).set("emb", "안녕", [0.1, 0.2])
    cache2 = SqliteCache(db)
    assert cache2.get("emb", "안녕") == [0.1, 0.2]


def test_sqlite_cache_ttl(tmp_path: Path):
    cache = SqliteCache(tmp_path / "ttl.sqlite")
    cache.set("ns", "k", "v", ttl_s=0.05)
    assert cache.get("ns", "k") == "v"
    time.sleep(0.1)
    assert cache.get("ns", "k") is None
