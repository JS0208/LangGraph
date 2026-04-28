from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router
from app.observability import counter_inc, histogram_observe
from app.observability.logging import init_logging, set_trace_id
from app.retrieval.real_clients import extract_company_year


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS")
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_logging()
    yield


app = FastAPI(title="GraphRAG Multi-Agent Backend", lifespan=lifespan)

# CORS — 기본 ``*`` (데모/로컬). 운영에서는 ``ALLOWED_ORIGINS=https://app.example.com,...``.
_origins = _allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False if _origins == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def request_id_and_metrics(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    set_trace_id(request_id)
    started = time.perf_counter()
    counter_inc(
        "http_requests_total",
        1.0,
        {"method": request.method, "path": _route_template(request)},
    )
    try:
        response = await call_next(request)
    except Exception:
        counter_inc(
            "http_request_errors_total",
            1.0,
            {"method": request.method, "path": _route_template(request)},
        )
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    histogram_observe(
        "http_request_duration_ms",
        elapsed_ms,
        {"method": request.method, "path": _route_template(request)},
        buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
    )
    response.headers["X-Request-Id"] = request_id
    return response


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path) if route else request.url.path


app.include_router(router)


async def cli_demo() -> None:
    init_logging()
    from app.agents.graph import build_graph

    graph = build_graph()
    query = input("질의를 입력하세요: ").strip()
    company, year = extract_company_year(query)
    state = {
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
    }
    async for update in graph.astream(state, stream_mode="updates"):
        print(update)


if __name__ == "__main__":
    asyncio.run(cli_demo())
