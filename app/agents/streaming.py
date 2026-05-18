"""Node-level true streaming buffer — Sprint 7 (Pillar 6 보강).

목적
- 노드 내부 LLM 호출(`router.stream(...)`) 의 token 을 **노드 종료 전**에 SSE 로
  내보낼 수 있도록 thread_id 별 asyncio.Queue 버퍼를 제공한다.
- ``endpoints.stream`` 은 이 큐를 polling 해 ``token`` 이벤트를 보낸다.

설계 원칙
- 의존성 0. 단일 프로세스 in-memory.
- 큐가 없으면 no-op (기존 노드 흐름 그대로).
- 노드 코드는 ``token_buffer.put_token(thread_id, "node_name", "delta")`` 만 호출.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from dataclasses import dataclass, field
from typing import AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class _ThreadBuffer:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    finished: bool = False


_active_thread: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "graphrag_thread_id", default=None
)
_buffers: dict[str, _ThreadBuffer] = {}
_lock = threading.Lock()


def set_active_thread(thread_id: str | None) -> None:
    _active_thread.set(thread_id)


def active_thread() -> str | None:
    return _active_thread.get()


def open_buffer(thread_id: str) -> _ThreadBuffer:
    with _lock:
        buf = _buffers.get(thread_id)
        if buf is None:
            buf = _ThreadBuffer()
            _buffers[thread_id] = buf
        else:
            buf.finished = False
        return buf


def close_buffer(thread_id: str) -> None:
    with _lock:
        buf = _buffers.get(thread_id)
        if buf is not None:
            buf.finished = True
            try:
                buf.queue.put_nowait(("__done__", ""))
            except Exception:  # noqa: BLE001
                pass


def discard_buffer(thread_id: str) -> None:
    with _lock:
        _buffers.pop(thread_id, None)


def put_token(thread_id: str | None, node: str, delta: str) -> None:
    if not thread_id or not delta:
        return
    with _lock:
        buf = _buffers.get(thread_id)
    if buf is None:
        return
    try:
        buf.queue.put_nowait((node, delta))
    except Exception:  # noqa: BLE001
        pass


async def drain_until_node_end(
    thread_id: str,
    *,
    poll_interval_s: float = 0.01,
    max_idle_loops: int = 200,
) -> AsyncIterator[tuple[str, str]]:
    """노드 1개 사이의 토큰을 흘려보낸다. 큐가 비고 idle loop 한도 도달 시 종료."""
    with _lock:
        buf = _buffers.get(thread_id)
    if buf is None:
        return
    idle = 0
    while True:
        try:
            node, delta = buf.queue.get_nowait()
        except asyncio.QueueEmpty:
            if buf.finished:
                return
            idle += 1
            if idle >= max_idle_loops:
                return
            await asyncio.sleep(poll_interval_s)
            continue
        idle = 0
        if node == "__done__":
            return
        yield node, delta


__all__ = [
    "set_active_thread",
    "active_thread",
    "open_buffer",
    "close_buffer",
    "discard_buffer",
    "put_token",
    "drain_until_node_end",
]
