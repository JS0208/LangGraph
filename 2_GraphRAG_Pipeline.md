2. GraphRAG 파이프라인 명세 (데이터 수집 및 적재)

[CURSOR AI 작업 지침]
이 문서는 DART API에서 데이터를 가져와 Neo4j(지식 그래프)와 Qdrant(벡터 DB)에 적재하고, 사용자 질의 시 두 DB를 병합 검색(Hybrid Search)하는 데이터 파이프라인 명세다.
이 구간은 네트워크 I/O 및 파싱 에러가 가장 빈번하게 발생하는 '지뢰밭'이다. 따라서 1인 개발 체제의 속도를 유지하기 위해 모든 외부 통신 구간에 'Fall-back(예외 우회)' 로직을 강제한다.

2.1. DART Open API 연동 및 파서 (app/retrieval/dart_parser.py)

DART API를 통해 재무제표 및 주요 공시를 파싱한다. 속도와 토큰 비용을 고려하여 아래 원칙을 준수하라.

스코프 제한: 초기 구축 시 삼성전자, SK하이닉스, 네이버, 카카오, LG CNS 5개 기업의 최근 3년 데이터로만 호출 범위를 한정한다.

비동기 I/O: aiohttp 또는 httpx를 사용하여 비동기(async)적으로 API를 호출하라.

🚨 [핵심 Fallback] Seed Data 강제 전환:

DART API의 Rate Limit에 걸리거나, JSON/XML 파싱 구조가 변경되어 KeyError 등이 발생할 경우, 절대 재시도 루프를 길게 돌리거나 복잡한 예외 처리로 시간을 낭비하지 마라.

즉시 에러를 Catch하고, 사전에 시스템에 준비된 tests/seed_data/mock_dart_response.json (수동 정제된 Mock 데이터)을 읽어와 정상 파싱된 것처럼 반환하는 try-except 블록을 최상단에 구성하라.

2.2. 지식 추출 및 임베딩 파이프라인 (app/retrieval/embedding_pipeline.py)

파싱된 원문 텍스트를 LLM에 통과시켜 엔티티와 관계를 추출(Graph용)하고, 동시에 텍스트 자체를 임베딩(Vector용)한다. 비용과 지연 시간을 통제하라.

Graph Extraction (LLM Structured Output):

LLM(Gemini 2.5 Pro 또는 Claude 3.5 Sonnet)에 텍스트 청크를 입력하여 docs/1_Data_Schema_and_State.md에 정의된 스키마 형식(Company, Subsidiary, FinancialReport, Disclosure)의 JSON 배열만 반환하도록 프롬프트를 구성하라.

추출된 JSON을 Neo4j Cypher 쿼리로 변환하는 json_to_cypher() 함수를 작성하되, 중복 노드 생성을 방지하기 위해 CREATE 대신 MERGE 구문을 사용하라.

Vector Embedding:

문서를 500~1000 토큰 단위로 청킹한 후 임베딩하여 Qdrant에 적재하라.

[필수] 1.3 스키마 지침에 따라 company_name, year 메타데이터를 Payload에 반드시 매핑하라.

2.3. 하이브리드 검색 라우터 (app/retrieval/query_router.py)

이 모듈은 LangGraph의 에이전트(특히 리스크 관리자나 재무 분석가 노드)가 컨텍스트를 찾기 위해 호출할 단일(Single) 진입점이다.

입력 매개변수: user_query (str)

내부 동작 로직:

Vector Search (Semantic): Qdrant에서 user_query와 의미론적으로 유사한 텍스트 청크 Top-K(예: 5개)를 조회한다.

Graph Search (Relational): * 질의에서 정규표현식이나 간단한 LLM 호출로 대상 기업명(Entity)을 추출한다.

추출된 Entity를 기준 노드로 삼아 Neo4j에서 인접 노드(최대 2-hop)의 연결 엣지 정보를 Cypher로 조회한다. (예: MATCH (c:Company {name: $name})-[r*1..2]-(n) RETURN c, r, n)

Context Merging: Vector 검색 결과(문서의 문맥적 사실)와 Graph 검색 결과(기업 간의 논리적 연결성)를 하나의 문자열 블록 또는 딕셔너리로 포맷팅하여 병합한다.

출력: LangGraph 상태 객체의 retrieved_context에 직접 주입할 수 있는 형태의 Dictionary.