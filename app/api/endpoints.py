from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from app.memory import get_episode_store, get_state_store
from app.observability import counter_inc, histogram_observe, metrics_registry
from app.observability.logging import get_logger, new_trace_id, set_trace_id
from app.retrieval.real_clients import extract_company_year
from app.security import (
    GuardrailVerdict,
    audit_event,
    classify_input,
    require_token,
    sanitize_text,
)

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

# 단일 노드 in-memory thread 사전(질의 텍스트 등). PostgresSaver 도입 전 임시.
THREADS: Dict[str, str] = {}

logger = get_logger("graphrag.api")


class AnalyzeRequest(BaseModel):
    query: str


class StateUpdate(BaseModel):
    """resume 시 사용자가 주입할 state 패치."""
    user_query: str | None = None
    target_company: str | None = None
    target_year: int | None = None
    extra: dict[str, Any] | None = None


# --- helpers ---------------------------------------------------------------


def _v1_payload(node: str, value: Any) -> str:
    return f"data: {json.dumps({node: value}, ensure_ascii=False)}\n\n"


def _v2_payload(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _summarize_node_payload(node: str, value: Any) -> dict[str, Any]:
    """v2 이벤트에 포함할 요약 정보."""
    summary: dict[str, Any] = {}
    if not isinstance(value, dict):
        return summary
    if node == "intent_classifier":
        summary["intent"] = value.get("intent")
    elif node == "retrieve_context":
        ctx = value.get("retrieved_context") or {}
        summary["mode"] = ctx.get("mode")
        summary["evidence_count"] = len(ctx.get("evidence", []) or [])
    elif node == "finance_analyst":
        fm = value.get("finance_metrics") or {}
        summary["debt_ratio"] = fm.get("debt_ratio")
        summary["source"] = fm.get("source")
    elif node == "risk_compliance":
        summary["risk_count"] = len(value.get("risk_points") or [])
    elif node == "critic":
        summary["disagreement_score"] = value.get("disagreement_score")
    elif node == "orchestrator":
        summary["consensus_reached"] = value.get("consensus_reached")
        summary["turn_count"] = value.get("turn_count")
    return summary


def _final_report_text(node: str, value: Any) -> str:
    """progressive token streaming 의 대상 텍스트.

    - ``orchestrator`` 노드의 마지막 message content
    - ``generate_final_report`` 의 ``final_report`` 필드 (있는 경우)
    """
    if not isinstance(value, dict):
        return ""
    if node == "orchestrator":
        messages = value.get("messages") or []
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, str):
                    return content
    if node == "generate_final_report":
        for key in ("final_report", "report", "summary"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _split_tokens(text: str, max_tokens: int = 60) -> list[str]:
    """token chunk 으로 분할. 한국어를 고려해 어절 단위 + 길이 제한 청크."""
    if not text:
        return []
    tokens = text.split(" ")
    out: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        out.append(tok + " ")
        if len(out) >= max_tokens:
            out.append("…")
            break
    return out


def _evidence_added_events(node: str, value: Any) -> list[dict[str, Any]]:
    if node != "retrieve_context" or not isinstance(value, dict):
        return []
    ctx = value.get("retrieved_context") or {}
    out: list[dict[str, Any]] = []
    for ev in ctx.get("evidence", []) or []:
        if not isinstance(ev, dict):
            continue
        out.append(
            {
                "type": "evidence_added",
                "evidence_id": ev.get("evidence_id"),
                "preview": ev.get("text_preview"),
                "source_type": ev.get("source_type"),
                "company_name": ev.get("company_name"),
            }
        )
    return out


# --- endpoints -------------------------------------------------------------


@router.post("/start")
async def start_analysis(
    payload: AnalyzeRequest, _user: dict[str, Any] = Depends(require_token)
) -> Dict[str, Any]:
    new_trace_id()
    verdict: GuardrailVerdict = classify_input(payload.query)
    counter_inc("graphrag_analyze_requests_total", 1.0, {"classification": verdict.classification})

    if verdict.classification == "prompt_injection":
        audit_event(
            "analyze.start.blocked",
            resource="analyze.start",
            result="prompt_injection",
            meta={"reasons": list(verdict.reasons)},
        )
        raise HTTPException(status_code=400, detail="prompt injection blocked")

    thread_id = str(uuid.uuid4())
    sanitized = sanitize_text(payload.query)
    THREADS[thread_id] = sanitized
    audit_event(
        "analyze.start",
        resource=thread_id,
        meta={"length": len(payload.query), "classification": verdict.classification},
    )
    return {"status": "started", "thread_id": thread_id}


async def _ping_emitter(queue: asyncio.Queue[str], stop: asyncio.Event, interval_s: float = 15.0) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            await queue.put(_v2_payload({"type": "ping", "ts": time.time()}))


@router.get("/stream/{thread_id}")
async def stream_analysis(
    thread_id: str, _user: dict[str, Any] = Depends(require_token)
) -> StreamingResponse:
    if thread_id not in THREADS:
        raise HTTPException(status_code=404, detail="thread_id not found")

    query = THREADS[thread_id]
    set_trace_id(thread_id)

    state_store = get_state_store()
    episode_store = get_episode_store()
    state_store.clear_interrupts(thread_id)

    async def event_stream() -> AsyncGenerator[str, None]:
        started = time.perf_counter()
        cancelled = False
        try:
            from app.agents.graph import build_graph

            company, year = extract_company_year(query)

            graph = build_graph()
            init_state = {
                "user_query": query,
                "target_company": company,
                "target_year": year,
                "messages": [],
                "turn_count": 0,
                "retrieved_context": {},
                "finance_metrics": {},
                "risk_points": [],
                "consensus_reached": False,
                "next_node": "intent_classifier",
                "evidence": [],
                "reflexion_count": 0,
                "disagreement_score": 0.0,
                "trace_id": thread_id,
            }
            current_state: dict[str, Any] = dict(init_state)
            state_store.save(thread_id, current_state)

            config = {"configurable": {"thread_id": thread_id}}

            yield _v2_payload({"type": "stream_start", "thread_id": thread_id, "ts": time.time()})
            audit_event("analyze.stream.start", resource=thread_id)

            ping_queue: asyncio.Queue[str] = asyncio.Queue()
            ping_stop = asyncio.Event()
            ping_task = asyncio.create_task(_ping_emitter(ping_queue, ping_stop))

            stream = graph.astream(init_state, config=config, stream_mode="updates")
            try:
                while True:
                    if state_store.is_cancel_requested(thread_id):
                        cancelled = True
                        consumed, reason = state_store.consume_cancel(thread_id)
                        yield _v2_payload(
                            {
                                "type": "interrupt_requested",
                                "reason": reason or "user_interrupt",
                                "thread_id": thread_id,
                                "consumed": consumed,
                            }
                        )
                        audit_event(
                            "analyze.stream.interrupt",
                            resource=thread_id,
                            result="ok",
                            meta={"reason": reason},
                        )
                        break

                    # ping 큐에서 모이면 즉시 전송
                    try:
                        ping_payload = ping_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        ping_payload = None
                    if ping_payload is not None:
                        yield ping_payload

                    try:
                        update = await asyncio.wait_for(anext(stream), timeout=30)
                    except StopAsyncIteration:
                        yield _sse_done()
                        break
                    except asyncio.TimeoutError:
                        yield _v2_payload(
                            {
                                "type": "error",
                                "code": "NODE_TIMEOUT",
                                "fallback": True,
                                "message": "노드 응답 지연으로 fallback 송출",
                            }
                        )
                        yield _v1_payload(
                            "system",
                            {"status": "error", "message": "[Fallback] 노드 응답 지연"},
                        )
                        yield _sse_done()
                        break

                    # update == {node_name: dict}
                    node, value = next(iter(update.items()))
                    summary = _summarize_node_payload(str(node), value)
                    yield _v2_payload(
                        {"type": "node_start", "node": node, "ts": time.time()}
                    )
                    yield _v1_payload(str(node), value)
                    for ev in _evidence_added_events(str(node), value):
                        yield _v2_payload(ev)

                    # generate_final_report / orchestrator 의 최종 요약 텍스트는
                    # 토큰 단위로 progressive 송출 (UX). v2 'token' 이벤트.
                    summary_text = _final_report_text(str(node), value)
                    if summary_text:
                        for token in _split_tokens(summary_text):
                            yield _v2_payload(
                                {
                                    "type": "token",
                                    "node": node,
                                    "delta": token,
                                }
                            )
                            counter_inc("graphrag_tokens_streamed_total", 1.0, {"node": str(node)})

                    yield _v2_payload(
                        {
                            "type": "node_end",
                            "node": node,
                            "ts": time.time(),
                            "summary": summary,
                        }
                    )
                    counter_inc("graphrag_node_visits_total", 1.0, {"node": str(node)})

                    if isinstance(value, dict):
                        current_state.update(value)
                    state_store.save(thread_id, current_state)

                duration_ms = (time.perf_counter() - started) * 1000.0
                histogram_observe(
                    "graphrag_stream_duration_ms",
                    duration_ms,
                    None,
                    buckets=(50, 100, 250, 500, 1000, 2000, 5000, 10000, 20000),
                )
                if not cancelled:
                    yield _v2_payload(
                        {"type": "done", "thread_id": thread_id, "duration_ms": duration_ms}
                    )
                    episode_store.record(
                        thread_id=thread_id,
                        query=query,
                        final_state=current_state,
                        duration_ms=duration_ms,
                    )
                    audit_event(
                        "analyze.stream.done",
                        resource=thread_id,
                        meta={"duration_ms": duration_ms},
                    )
            finally:
                ping_stop.set()
                ping_task.cancel()
                try:
                    await ping_task
                except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                    pass
        except Exception as e:
            import traceback

            traceback.print_exc()
            counter_inc("graphrag_stream_errors_total", 1.0)
            audit_event(
                "analyze.stream.error",
                resource=thread_id,
                result="error",
                meta={"error": str(e)},
            )
            fallback = {"system": {"status": "error", "message": f"[Fallback] AI 호출 오류: {str(e)}"}}
            yield f"data: {json.dumps(fallback, ensure_ascii=False)}\n\n"
            yield _v2_payload({"type": "error", "code": "STREAM_FAILURE", "message": str(e)})
            yield _sse_done()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/interrupt/{thread_id}")
async def interrupt_analysis(
    thread_id: str,
    reason: str | None = None,
    _user: dict[str, Any] = Depends(require_token),
) -> Dict[str, Any]:
    if thread_id not in THREADS:
        raise HTTPException(status_code=404, detail="thread_id not found")
    get_state_store().request_cancel(thread_id, reason or "user_interrupt")
    audit_event(
        "analyze.interrupt.request",
        resource=thread_id,
        meta={"reason": reason},
    )
    counter_inc("graphrag_interrupts_total", 1.0)
    return {"status": "interrupt_queued", "thread_id": thread_id, "reason": reason}


@router.get("/state/{thread_id}")
async def state_analysis(
    thread_id: str, _user: dict[str, Any] = Depends(require_token)
) -> Dict[str, Any]:
    snap = get_state_store().snapshot(thread_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="state not found")
    return {"thread_id": thread_id, "state": snap}


@router.post("/resume/{thread_id}")
async def resume_analysis(
    thread_id: str,
    patch: StateUpdate,
    _user: dict[str, Any] = Depends(require_token),
) -> StreamingResponse:
    state_store = get_state_store()
    snap = state_store.snapshot(thread_id)
    if snap is None and thread_id not in THREADS:
        raise HTTPException(status_code=404, detail="thread_id not found")

    base = snap or {}
    if patch.user_query:
        base["user_query"] = patch.user_query
        THREADS[thread_id] = patch.user_query
    if patch.target_company is not None:
        base["target_company"] = patch.target_company
    if patch.target_year is not None:
        base["target_year"] = patch.target_year
    if patch.extra:
        base.update(patch.extra)

    base.setdefault("messages", [])
    base.setdefault("turn_count", 0)
    base.setdefault("retrieved_context", {})
    base.setdefault("finance_metrics", {})
    base.setdefault("risk_points", [])
    base.setdefault("consensus_reached", False)
    base.setdefault("evidence", [])
    base.setdefault("reflexion_count", 0)
    base.setdefault("disagreement_score", 0.0)
    base["next_node"] = "retrieve_context"  # resume 후에는 정상 파이프라인 진입
    state_store.save(thread_id, base)
    state_store.clear_interrupts(thread_id)
    audit_event(
        "analyze.resume",
        resource=thread_id,
        meta={"keys_patched": [k for k in ("user_query", "target_company", "target_year") if getattr(patch, k) is not None]},
    )
    counter_inc("graphrag_resumes_total", 1.0)

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            from app.agents.graph import build_graph

            graph = build_graph()
            yield _v2_payload({"type": "stream_resume", "thread_id": thread_id, "ts": time.time()})
            stream = graph.astream(dict(base), config={"configurable": {"thread_id": thread_id}}, stream_mode="updates")
            current_state = dict(base)
            try:
                while True:
                    try:
                        update = await asyncio.wait_for(anext(stream), timeout=30)
                    except StopAsyncIteration:
                        yield _sse_done()
                        return
                    node, value = next(iter(update.items()))
                    yield _v2_payload({"type": "node_start", "node": node, "ts": time.time()})
                    yield _v1_payload(str(node), value)
                    yield _v2_payload({"type": "node_end", "node": node, "ts": time.time(), "summary": _summarize_node_payload(str(node), value)})
                    if isinstance(value, dict):
                        current_state.update(value)
                    state_store.save(thread_id, current_state)
                yield _v2_payload({"type": "done", "thread_id": thread_id})
            except Exception as exc:  # noqa: BLE001
                yield _v2_payload({"type": "error", "code": "RESUME_FAILURE", "message": str(exc)})
                yield _sse_done()
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'system': {'status': 'error', 'message': str(e)}}, ensure_ascii=False)}\n\n"
            yield _sse_done()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/episodes")
async def list_episodes(
    limit: int = 20, _user: dict[str, Any] = Depends(require_token)
) -> Dict[str, Any]:
    episodes = get_episode_store().latest(limit=max(1, min(limit, 100)))
    return {"count": len(episodes), "episodes": episodes}


# --- /metrics & /health ---------------------------------------------------


@router.get("/health", include_in_schema=False)
async def health() -> Dict[str, Any]:
    return {"status": "ok", "ts": time.time()}


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
async def metrics_endpoint() -> str:
    return metrics_registry().prometheus_text()


__all__ = ["router"]
