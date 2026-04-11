from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])
THREADS: Dict[str, str] = {}


class AnalyzeRequest(BaseModel):
    query: str


@router.post("/start")
async def start_analysis(payload: AnalyzeRequest) -> Dict[str, Any]:
    thread_id = str(uuid.uuid4())
    THREADS[thread_id] = payload.query
    return {"status": "started", "thread_id": thread_id}


@router.get("/stream/{thread_id}")
async def stream_analysis(thread_id: str) -> StreamingResponse:
    if thread_id not in THREADS:
        raise HTTPException(status_code=404, detail="thread_id not found")

    query = THREADS[thread_id]

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            from app.agents.graph import build_graph

            graph = build_graph()
            init_state = {
                "user_query": query,
                "messages": [],
                "turn_count": 0,
                "retrieved_context": {},
                "finance_metrics": {},
                "risk_points": [],
                "consensus_reached": False,
                "next_node": "retrieve_context",
            }
            config = {"configurable": {"thread_id": thread_id}}
            stream = graph.astream(init_state, config=config, stream_mode="updates")
            while True:
                try:
                    update = await asyncio.wait_for(anext(stream), timeout=30)
                except StopAsyncIteration:
                    break
                yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"
        except Exception:
            fallback = {"node": "system", "status": "error", "message": "[Fallback] AI 분석 지연 또는 오류로 기본 리스크 시나리오를 반환합니다."}
            yield f"data: {json.dumps(fallback, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
