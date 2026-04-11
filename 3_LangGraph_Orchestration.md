3. LangGraph 기반 오케스트레이션 엔진 명세 (핵심 로직)

[CURSOR AI 작업 지침]
이 문서는 LangGraph를 활용한 다중 에이전트(Multi-Agent) 턴제 토론 시스템의 아키텍처 명세다. LLM 에이전트들은 자유도를 주면 서로 의미 없는 대화를 반복하며 무한 루프(Deadlock)에 빠지기 쉽다. 따라서 아래 명시된 **'엄격한 라우팅 규칙'**과 '구조화된 출력(Structured Output)' 원칙을 절대적으로 준수하여 코드를 작성하라.

3.1. 에이전트 노드(Node) 정의 및 역할 (app/agents/nodes.py)

각 노드는 docs/1_Data_Schema_and_State.md에 정의된 GraphState를 입력으로 받고, 상태를 업데이트할 Dictionary를 반환하는 Python 비동기 함수(async def)로 구현하라.

1. finance_analyst_node (재무 분석가)

역할: retrieved_context 내의 정량적 데이터(재무제표, 영업이익률 등)를 바탕으로 수익성 및 재무 리스크를 분석.

출력 강제 (Structured Output): 프롬프트를 작성할 때 반드시 JSON 형식(예: {"finance_metrics": {"debt_ratio": "200%", "insight": "부채 비율 과다"}})으로만 답변하도록 Pydantic Parser나 LLM의 JSON Mode 기능을 강제하라. 서술형 답변(Yapping)은 시스템을 망가뜨린다.

상태 업데이트: finance_metrics 필드 업데이트 및 messages 리스트에 본인의 분석 의견 추가.

2. risk_compliance_node (규제/리스크 관리자)

역할: retrieved_context 내의 정성적 데이터(소송, 지분 변동, 공시 등)를 바탕으로 법적/경영권 리스크 도출.

출력 강제: 이 노드 역시 {"risk_points": ["자회사 A 소송 진행 중", "유상증자로 인한 지분 희석 우려"]} 형태의 JSON 배열 구조로만 출력하도록 강제하라.

상태 업데이트: risk_points 필드 업데이트 및 messages 리스트에 의견 추가.

3. orchestrator_node (오케스트레이터 및 합의 도출)

역할: 재무 분석가와 리스크 관리자의 의견을 종합하여 최종 투자/의사결정 합의문(Consensus)을 작성하고 토론을 종료할지 결정한다.

상태 업데이트: * turn_count를 1 증가시킨다. (state['turn_count'] + 1)

두 에이전트의 의견이 일치하거나 충분히 조율되었다고 판단되면 consensus_reached = True로 설정한다.

3.2. 조건부 엣지 및 라우팅 로직 (app/agents/edges.py)

LangGraph의 add_conditional_edges를 활용하여 흐름을 제어한다. 여기서 핵심은 **안전 장치(Circuit Breaker)**다.

라우팅 함수 명세 (router_logic)

GraphState를 인자로 받아 다음 이동할 노드의 이름(문자열)을 반환한다.

[🚨 최우선 원칙] turn_count >= 3 (또는 환경변수로 설정된 MAX_TURNS) 인지 가장 먼저 검사하라. 만약 최대 턴 수에 도달했다면, consensus_reached 여부와 상관없이 강제로 generate_final_report 노드로 라우팅하여 토론을 강제 종료시켜라. (무한 API 호출 비용 방지)

최대 턴 수가 아니라면, 오케스트레이터의 판단에 따라 누락된 정보가 있는 쪽(finance_analyst 또는 risk_compliance)으로 턴을 넘긴다.

3.3. 그래프 조립 및 컴파일 (app/agents/graph.py)

StateGraph(GraphState) 인스턴스를 생성하고, 위의 노드들과 엣지를 연결하라.

엔터프라이즈 요구사항(추후 Human-in-the-Loop 적용)을 대비하여 컴파일 시 checkpointer=MemorySaver()를 반드시 추가하여 상태(State)가 메모리에 보존되도록 구성하라.