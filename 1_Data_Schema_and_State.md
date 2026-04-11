1. 핵심 데이터 스키마 및 상태(State) 정의

[CURSOR AI 작업 지침]
이 문서는 GraphRAG 파이프라인과 LangGraph 에이전트 간의 데이터 흐름을 통제하는 '절대적인 스키마 표준'이다.
코드 생성 시 반드시 아래 명시된 타입 힌트(Type Hints)와 스키마 구조를 준수하라. 임의로 필드를 추가하거나 삭제하지 마라.

1.1. LangGraph State Object 구조 (app/state.py)

다중 에이전트(재무 분석가, 리스크 관리자, 오케스트레이터)가 공유하는 전역 상태(State)이다. 에이전트 간의 메시지 핑퐁으로 인한 무한 루프를 방지하기 위해 turn_count와 consensus_reached를 강제한다. Python의 TypedDict를 사용하여 엄격하게 타입을 제어하라.

from typing import TypedDict, List, Dict, Any, Annotated
import operator

class GraphState(TypedDict):
    # 사용자 초기 질의
    user_query: str
    
    # 누적된 대화 기록 (에이전트 간 토론 내용 포함)
    # Annotated를 사용하여 메시지가 덮어씌워지지 않고 append 되도록 처리
    messages: Annotated[List[Dict[str, str]], operator.add]
    
    # 현재 토론 턴 수 (Deadlock 방지용, 최대 3~5턴으로 제한)
    turn_count: int
    
    # GraphRAG에서 추출된 컨텍스트 (Neo4j 및 Qdrant 검색 결과)
    retrieved_context: Dict[str, Any]
    
    # 각 에이전트가 도출한 핵심 인사이트
    finance_metrics: Dict[str, Any]  # Agent A (재무) 도출 결과
    risk_points: List[str]           # Agent B (리스크) 도출 결과
    
    # 합의 도출 여부 (True일 경우 최종 응답 생성 노드로 라우팅)
    consensus_reached: bool
    
    # 다음으로 실행될 에이전트 라우팅 키
    next_node: str


1.2. Neo4j 지식 그래프 스키마 (Graph Schema)

초기 MVP 단계에서는 상위 5대 IT 기업으로 스코프를 제한하므로, 스키마를 무겁게 가져가지 않는다. 아래 정의된 Node Label과 Relationship Type 외에는 생성하지 마라.

[Node Labels]

Company: 기업 본체 (속성: name, stock_code, market_cap)

Subsidiary: 자회사 (속성: name, business_type)

FinancialReport: 재무제표 항목 (속성: year, quarter, revenue, operating_profit, debt_ratio)

Disclosure: 공시/이벤트 (속성: date, event_type, summary) # 예: 소송, 유상증자, M&A

[Relationships (Edges)]

(Company)-[:OWNS {share_ratio: float}]->(Subsidiary): 지분 소유 관계

(Company)-[:HAS_REPORT]->(FinancialReport): 재무 실적 보유

(Company|Subsidiary)-[:INVOLVED_IN]->(Disclosure): 리스크/공시 연관성

[Fallback 지시] Neo4j DB 연결이 실패하거나 Cypher 쿼리 파싱이 지연될 경우, 위 스키마를 모방한 NetworkX 기반의 In-memory 그래프를 반환하는 mock_graph_client.py를 대안으로 작성할 준비를 하라.

1.3. Qdrant 벡터 데이터베이스 메타데이터 스키마

텍스트 청크(Chunk)를 벡터화하여 저장할 때, 하이브리드 검색(Hybrid Search) 시 필터링 성능을 극대화하기 위해 아래 메타데이터 스키마를 Payload에 반드시 포함하라.

chunk_id: 고유 식별자 (UUID)

source_type: 데이터 출처 ("DART_REPORT", "NEWS", "DISCLOSURE")

company_name: 연관 기업명 (예: "삼성전자")

year: 해당 데이터의 연도 (정수형, 예: 2025)

text_content: 원문 청크 텍스트

[라우팅 지시] 사용자의 질의가 특정 기업과 연도를 지칭할 경우, 의미론적 검색(Semantic Search)을 수행하기 전에 Qdrant의 Payload Filter(company_name, year)를 우선 적용하여 검색 범위를 좁히는 로직을 구현하라.