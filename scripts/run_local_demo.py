from __future__ import annotations

import asyncio

from app.agents.graph import build_graph


async def main() -> None:
    graph = build_graph()
    state = {
        "user_query": "카카오 2024년 3분기 실적과 자회사 규제 리스크를 분석해줘",
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
    asyncio.run(main())
