from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict, Optional

class GraphState(TypedDict):
    user_query: str
    target_company: Optional[str]  # 강제 주입될 기업명
    target_year: Optional[int]     # 강제 주입될 연도
    messages: Annotated[List[Dict[str, str]], operator.add]
    turn_count: int
    retrieved_context: Dict[str, Any]
    finance_metrics: Dict[str, Any]
    risk_points: List[str]
    consensus_reached: bool
    next_node: str