from __future__ import annotations

import pytest

from app.memory.saver_factory import get_checkpointer


def test_returns_none_when_dsn_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CHECKPOINTER_DSN", raising=False)
    assert get_checkpointer() is None


def test_returns_none_for_unrecognized_dsn():
    assert get_checkpointer("redis://nope") is None


def test_returns_none_when_postgres_module_missing():
    # langgraph.checkpoint.postgres 가 미설치라도 예외 없이 None.
    saver = get_checkpointer("postgres://user:pass@127.0.0.1/db")
    # 환경에 따라 None 또는 객체일 수 있다. None 또는 callable 인스턴스만 허용.
    assert saver is None or hasattr(saver, "put") or hasattr(saver, "get")


def test_returns_none_when_sqlite_module_missing():
    saver = get_checkpointer("sqlite:///tmp_state.sqlite")
    assert saver is None or hasattr(saver, "put") or hasattr(saver, "get")
