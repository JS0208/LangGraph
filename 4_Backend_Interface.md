4. 백엔드 인터페이스 명세 (FastAPI)

[CURSOR AI 작업 지침]
이 문서는 사용자의 질의를 받아 GraphRAG 파이프라인과 LangGraph 엔진을 트리거하고, 그 결과를 실시간으로 프론트엔드(또는 터미널)에 쏘아주는 FastAPI 백엔드 명세다.
추후 Vercel AI SDK 연동을 고려하여 반드시 Server-Sent Events (SSE) 방식의 비동기 스트리밍(StreamingResponse)으로 구현하라.

4.1. 메인 애플리케이션 및 라우터 설정 (app/main.py)

FastAPI 초기화: 비동기 I/O를 최적화한 FastAPI 앱 객체를 생성한다.

CORS 미들웨어: 추후 연동될 프론트엔드(Next.js, localhost:3000)와의 통신을 위해 CORS(Cross-Origin Resource Sharing)를 전면 개방(allow_origins=["*"])하는 미들웨어를 반드시 추가하라.

의존성 주입(Dependency Injection): 그래프 엔진 인스턴스와 데이터베이스 클라이언트(Qdrant, Neo4j)는 앱 시작 시(lifespan 이벤트) 한 번만 초기화하여 주입되도록 설계하라.

4.2. 핵심 API 엔드포인트 명세 (app/api/endpoints.py)

1. POST /api/v1/analyze/start

역할: 사용자 질의를 받아 새로운 분석 세션(Thread)을 생성한다.

Request Body: {"query": "삼성전자 3분기 실적과 관련된 자회사 M&A 리스크를 분석해줘"}

Response: LangGraph의 상태 추적을 위한 고유 thread_id (UUID) 반환.

{
  "status": "started",
  "thread_id": "123e4567-e89b-12d3-a456-426614174000"
}


2. GET /api/v1/analyze/stream/{thread_id} 🚨 (핵심 로직)

역할: 특정 thread_id의 LangGraph 실행 과정을 SSE(Server-Sent Events) 형식으로 스트리밍한다.

구현 지침:

FastAPI의 StreamingResponse(media_type="text/event-stream")를 사용하라.

LangGraph의 비동기 스트리밍 메서드인 graph.astream(..., stream_mode="updates")를 호출하라.

각 에이전트(노드)가 작업을 마칠 때마다 아래와 같은 포맷으로 데이터를 yield 하라.

data: {"node": "orchestrator", "status": "searching_graph", "message": "지식 그래프 검색 중..."} \n\n
data: {"node": "finance_analyst", "status": "analyzing", "content": "부채비율 200% 확인..."} \n\n


4.3. 🚨 예외 처리 및 Fallback 시나리오 강제

프론트엔드 UI 스트리밍은 에러가 발생하면 화면이 멈추거나 깨진다. 백엔드에서 절대 500 에러를 그대로 노출하지 마라.

시간 초과(Timeout) 방어: LLM 응답이 30초 이상 지연될 경우, asyncio.wait_for를 사용하여 강제로 타임아웃을 발생시키고 아래의 Fallback 메시지를 스트리밍하라.
data: {"node": "system", "status": "error", "message": "[Fallback] AI 분석 지연으로 기본 리스크 시나리오를 반환합니다."} \n\n

단독 실행(Terminal) 모드 지원:

if __name__ == "__main__": 블록을 활용하여, 서버를 띄우지 않고도 python app/main.py 실행 시 콘솔에서 바로 사용자 입력을 받고 그래프 결과를 print() 해주는 CLI 테스터 함수를 반드시 포함하라. (중간 평가 시연용)