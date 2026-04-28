from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

# Sprint 1: 신규 스키마/메타 export. import-only 사이드이펙트 없음.
from app.schemas import STATE_SCHEMA_VERSION  # noqa: F401  (외부에서 참조)


class GraphState(TypedDict, total=False):
    """LangGraph 다중 에이전트 공유 상태.

    하위호환을 위해 ``total=False`` 로 선언했고, 모든 신규 필드는 Optional 이다.
    Sprint 0~1 시점의 기존 호출자(`endpoints.py`, `cli_demo`)는 변경 없이 동작한다.
    Sprint 3 이후 신규 필드들이 점진적으로 채워진다.
    """

    # --- 기존 필드 (변경 금지) ---
    user_query: str
    target_company: Optional[str]
    target_year: Optional[int]
    messages: Annotated[List[Dict[str, str]], operator.add]
    turn_count: int
    retrieved_context: Dict[str, Any]
    finance_metrics: Dict[str, Any]
    risk_points: List[str]
    consensus_reached: bool
    next_node: str

    # --- Sprint 1 신규 (모두 Optional, 미설정 시 기존 흐름 유지) ---
    schema_version: str
    intent: str                          # QueryIntent literal
    query_plan: Dict[str, Any]           # QueryPlan.model_dump()
    evidence: Annotated[List[Dict[str, Any]], operator.add]   # Evidence.model_dump() 누적
    critic_report: Dict[str, Any]
    disagreement_score: float
    reflexion_count: int
    trace_id: str
    cost_usd: float
