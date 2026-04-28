"""구조화 로깅 — Sprint 5.

structlog 우선 사용. 미설치 환경에서는 stdlib logging 의 JSON formatter 로 회귀.
모든 로그는 ``trace_id`` 컨텍스트를 가진다.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

_trace_id: ContextVar[str | None] = ContextVar("graphrag_trace_id", default=None)


def new_trace_id() -> str:
    tid = uuid.uuid4().hex
    _trace_id.set(tid)
    return tid


def set_trace_id(trace_id: str | None) -> None:
    _trace_id.set(trace_id)


def get_trace_id() -> str | None:
    return _trace_id.get()


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        tid = _trace_id.get()
        if tid:
            payload["trace_id"] = tid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_initialized = False


def init_logging(level: int = logging.INFO) -> None:
    """프로세스 1회 초기화. 중복 호출 안전."""
    global _initialized
    if _initialized:
        return
    try:
        import structlog  # type: ignore[import-not-found]

        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                _structlog_trace_processor,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            cache_logger_on_first_use=True,
        )
        # stdlib logging 도 동일 포맷으로 회귀 출력 (외부 라이브러리 호환).
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logging.basicConfig(level=level, handlers=[handler], force=True)
    except ImportError:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logging.basicConfig(level=level, handlers=[handler], force=True)
    _initialized = True


def _structlog_trace_processor(_logger, _name, event_dict):  # type: ignore[no-untyped-def]
    tid = _trace_id.get()
    if tid:
        event_dict.setdefault("trace_id", tid)
    return event_dict


def get_logger(name: str = "graphrag") -> Any:
    init_logging()
    try:
        import structlog  # type: ignore[import-not-found]

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


__all__ = [
    "init_logging",
    "get_logger",
    "new_trace_id",
    "set_trace_id",
    "get_trace_id",
]
