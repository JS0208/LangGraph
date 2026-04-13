# GraphRAG Multi-Agent Demo

이 저장소는 기업 재무/공시 데이터를 바탕으로 질의를 분석하는 GraphRAG 기반 다중 에이전트 데모입니다.
백엔드는 FastAPI + LangGraph(미설치 시 local fallback), 프론트엔드는 Next.js 대시보드와 정적 프로토타입으로 구성되어 있습니다.

## 현재 상태

- 기본 실행 경로는 `fallback-first` 입니다.
- `Neo4j`, `Qdrant`, `LLM` 환경변수가 모두 준비되지 않아도 seed 데이터 기반으로 동작합니다.
- API 서버 실행은 `uvicorn app.main:app --reload --port 8000` 입니다.
- `python app/main.py`는 HTTP 서버가 아니라 콘솔용 `cli_demo()`를 실행합니다.
- 실데이터 적재 스크립트 `scripts/real_ingest.py`는 별도 실연동 자격 증명과 추가 의존성이 필요합니다.

## 폴더 구조

- `app/`: FastAPI 앱, LangGraph 노드/라우팅, 검색 계층
- `frontend_app/`: Next.js 16 대시보드
- `frontend_prototype/`: 정적 HTML 프로토타입
- `scripts/`: 사전 점검, 감사, 실데이터 적재 스크립트
- `tests/`: `pytest` 기반 회귀 테스트

## 빠른 시작

### 1. 백엔드

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API가 뜨면 `http://localhost:8000/docs`에서 엔드포인트를 확인할 수 있습니다.

### 2. 프론트엔드 대시보드

```bash
cd frontend_app
npm install
npm run dev
```

- 기본 백엔드 주소는 `http://localhost:8000`입니다.
- 다른 주소를 쓰려면 `frontend_app/.env.local`에 `NEXT_PUBLIC_API_URL=http://localhost:8000` 형태로 지정합니다.

### 3. 정적 프로토타입

```bash
python -m http.server 5500
```

이후 `http://localhost:5500/frontend_prototype/index.html`로 접속합니다.

## 환경 변수

기본 템플릿은 `.env.example`에 있습니다.

- 검색/DB 연동: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`
- LLM 연동: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- 실데이터 적재: `DART_API_KEY`
- 프론트엔드: `NEXT_PUBLIC_API_URL`

## 테스트와 점검

```bash
pytest -q
python scripts/preflight_check.py
python scripts/audit_project.py
```

프론트엔드 점검:

```bash
cd frontend_app
npm run lint
```

## 동작 방식 요약

1. `POST /api/v1/analyze/start`가 `thread_id`를 생성합니다.
2. `GET /api/v1/analyze/stream/{thread_id}`가 SSE로 노드별 업데이트를 전송합니다.
3. `app/retrieval/query_router.py`는 실연동이 가능하면 실제 조회를, 실패하면 seed fallback을 반환합니다.
4. `app/agents/graph.py`는 `langgraph` 미설치 환경에서도 `LocalFallbackGraph`로 실행됩니다.

## 알려진 제약

- 실연동 경로는 아직 운영 검증 전 단계입니다.
- `scripts/real_ingest.py`는 실제 키/DB/API quota를 전제로 합니다.
- SSE 이벤트 스키마는 현재 동작은 안정적이지만 별도 계약 문서 수준으로 고정되지는 않았습니다.
- 배포, 보안 스캔, 운영 파이프라인은 아직 사람 주도 작업이 남아 있습니다.

## 문서 인덱스

- `0_System_Context.md`: 시스템/개발 원칙
- `1_Data_Schema_and_State.md`: 상태/스키마 기준
- `2_GraphRAG_Pipeline.md`: 수집/적재/검색 파이프라인
- `3_LangGraph_Orchestration.md`: 오케스트레이션 규칙
- `4_Backend_API_and_SSE.md`: FastAPI/SSE 인터페이스
- `5_Frontend_and_QA.md`: 프론트엔드/QA 기준
- `6_Project_Status_and_Next_Steps.md`: 현재 제품 상태와 남은 과제
- `7_Progress_Dashboard.md`: 요약 상태판
- `8_Runtime_Runbook.md`: 실행 명령과 운영 메모
- `CURSOR_LOG.md`: 최근 문서/코드 정비 로그
- `9_Human_Required_Tasks.md`: 사람 승인/운영 작업
- `10_Real_Integration_Playbook.md`: 실연동 절차
- `11_Product_Blueprint.md`: 장기 제품 완성 청사진
- `12_UX_UI_Master_Plan.md`: UX/UI 원칙과 화면 방향
- `13_Selected_Ingestion_Checklist.md`: 5개 회사 2023~2026 선별 적재 기준
