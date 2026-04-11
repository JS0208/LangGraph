from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict


class GraphState(TypedDict):
    user_query: str
    messages: Annotated[List[Dict[str, str]], operator.add]
    turn_count: int
    retrieved_context: Dict[str, Any]
    finance_metrics: Dict[str, Any]
    risk_points: List[str]
    consensus_reached: bool
    next_node: str
