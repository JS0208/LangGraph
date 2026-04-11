from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="GraphRAG Multi-Agent Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


async def cli_demo() -> None:
    from app.agents.graph import build_graph

    graph = build_graph()
    query = input("질의를 입력하세요: ").strip()
    state = {
        "user_query": query,
        "messages": [],
        "turn_count": 0,
        "retrieved_context": {},
        "finance_metrics": {},
        "risk_points": [],
        "consensus_reached": False,
        "next_node": "retrieve_context",
    }
    async for update in graph.astream(state, stream_mode="updates"):
        print(update)


if __name__ == "__main__":
    asyncio.run(cli_demo())
