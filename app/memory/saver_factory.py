"""LangGraph Checkpointer Factory — Sprint 4/6 wire-compatible 어댑터.

목적
- 운영 환경에서 ``langgraph.checkpoint.postgres.PostgresSaver`` 가용 시 사용.
- dev 환경에서 ``langgraph.checkpoint.sqlite.SqliteSaver`` 가용 시 사용.
- 둘 다 미설치인 환경에서는 ``None`` 을 반환해 graph 가 메모리 모드로 동작하도록 한다.

본 함수는 import 실패에 안전하다. 외부 의존을 강제하지 않으며,
``CHECKPOINTER_DSN`` 환경변수가 비어 있으면 즉시 None 을 반환한다.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _try_postgres_saver(dsn: str) -> Any | None:
    if not dsn or not dsn.lower().startswith(("postgres://", "postgresql://")):
        return None
    try:
        module = importlib.import_module("langgraph.checkpoint.postgres")
        cls = getattr(module, "PostgresSaver", None)
        if cls is None:
            return None
        return cls.from_conn_string(dsn)  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostgresSaver 초기화 실패 — 회귀: %s", exc)
        return None


def _try_sqlite_saver(dsn: str) -> Any | None:
    if not dsn or not (dsn.lower().startswith("sqlite") or dsn.endswith(".sqlite")):
        return None
    try:
        module = importlib.import_module("langgraph.checkpoint.sqlite")
        cls = getattr(module, "SqliteSaver", None)
        if cls is None:
            return None
        return cls.from_conn_string(dsn)  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        logger.warning("SqliteSaver 초기화 실패 — 회귀: %s", exc)
        return None


def get_checkpointer(dsn: str | None = None) -> Any | None:
    """가능한 LangGraph 체크포인터를 반환. 미가용 시 None.

    호출자는 None 을 받으면 in-memory 경로로 graph 를 빌드해야 한다.
    """
    dsn_value = dsn or os.getenv("CHECKPOINTER_DSN", "").strip()
    if not dsn_value:
        return None

    saver = _try_postgres_saver(dsn_value) or _try_sqlite_saver(dsn_value)
    if saver is None:
        logger.info("checkpointer DSN '%s' — 사용 가능한 saver 없음, 메모리 모드", dsn_value[:40])
    return saver


__all__ = ["get_checkpointer"]
