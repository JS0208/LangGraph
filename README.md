# GraphRAG Multi-Agent Financial Analyst

> **LLM 오케스트레이션 기반 기업 재무 분석 멀티에이전트 시스템**  
> LLM-orchestrated multi-agent system for corporate financial analysis

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.4-1C3A5E?logo=langchain&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-GraphDB-008CC1?logo=neo4j&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-VectorDB-FF6B6B)
![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?logo=prometheus&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Tracing-425CC7)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)

---

## 프로젝트 소개

기업 공시(DART) 및 재무 데이터를 기반으로 자연어 질의를 분석하는 **GraphRAG 기반 멀티에이전트 시스템**입니다.  
LangGraph로 오케스트레이션한 8개 전문화 에이전트가 의도 분류 → 컨텍스트 검색 → 재무 분석 → 리스크 감사 → 반성·비평 → 최종 보고서 생성의 파이프라인을 실시간으로 처리합니다.

```
This project is a GraphRAG-based multi-agent system that analyzes natural language queries
against corporate financial data (DART filings). Eight specialized LangGraph agents handle
intent classification, hybrid retrieval, financial analysis, risk auditing, critic/reflection,
and final report generation — all streamed in real-time via SSE.
```

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Client (Next.js)                     │
│         POST /start  ──►  GET /stream/{thread_id}       │
└────────────────────────┬────────────────────────────────┘
                         │  SSE (Server-Sent Events)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI  (RESTful API + SSE Layer)          │
│  JWT Auth · Guardrail · Sanitize · Audit Log            │
│  asyncio Queue  ──  ping emitter (15s keepalive)        │
│  30s node timeout · cancel polling · finally cleanup    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph Orchestrator (8 nodes)           │
│                                                         │
│  intent_classifier → retrieve_context                   │
│       → finance_analyst → risk_compliance               │
│       → critic → reflector                             │
│       → orchestrator → generate_final_report            │
└────────┬──────────────────────────┬─────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐      ┌──────────────────────────────┐
│  Neo4j          │      │  Qdrant                      │
│  (Graph DB)     │      │  (Vector DB)                 │
│  관계·멀티홉    │      │  임베딩 유사도 검색           │
│  컨텍스트 추적  │      │  Hybrid Search (BM25+Dense)  │
└─────────────────┘      └──────────────────────────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
         Hybrid Retrieval (그래프 + 벡터 결합)
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│          Observability (Prometheus + OTel)              │
│  노드별 지연·오류·트래픽 메트릭  /metrics endpoint      │
│  분산 추적 스팬  /traces/{trace_id} endpoint            │
└─────────────────────────────────────────────────────────┘
```

---

## 핵심 기능

### 🔄 실시간 SSE 스트리밍
- `POST /start` → `GET /stream/{thread_id}` 구조의 비동기 스트리밍 파이프라인
- asyncio Queue 기반 `ping 에미터` (15초 간격 keepalive) — 프록시·방화벽 유휴 타임아웃 방지
- 노드 응답 30초 초과 시 `TimeoutError` catch → fallback 이벤트 송출 후 graceful 종료
- 사용자 명시적 중단: `POST /interrupt/{thread_id}` + cancel 폴링 → `finally` 태스크 정리

### 🧠 LangGraph 멀티에이전트 오케스트레이션
- 8개 전문화 에이전트 파이프라인 (의도 분류 → 보고서 생성)
- 비평·반성(Critic/Reflector) 노드로 품질 자가검증 루프
- 에이전트 간 상태 공유 및 인터럽트 지원

### 🔍 하이브리드 검색 (GraphRAG)
- Neo4j 그래프 DB: 기업·문서 간 관계 추적, 멀티홉 컨텍스트 검색
- Qdrant 벡터 DB: 임베딩 유사도 검색 (BM25 + Dense 결합)
- DART API 연동 기업 공시 데이터 적재

### 📊 지능형 모니터링
- Prometheus 메트릭: 노드 방문 수, 스트림 지속 시간(히스토그램), 오류율, 토큰 수
- OpenTelemetry 분산 추적: span tree로 에이전트 실행 경로 추적
- `/metrics`, `/traces/{trace_id}` 전용 엔드포인트

### 🔒 보안 계층
- JWT 기반 Bearer 토큰 인증 (`require_token` 의존성)
- 가드레일: 프롬프트 인젝션 분류·차단 (`GuardrailVerdict`)
- 입력 sanitize + 감사 로그 (`audit_event`) 전 엔드포인트 적용

---

## 기술 스택

| 분류 | 기술 |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn |
| Agent Orchestration | LangGraph, LangChain |
| Streaming | SSE (Server-Sent Events), asyncio |
| Graph DB | Neo4j (bolt+s) |
| Vector DB | Qdrant |
| Monitoring | Prometheus, OpenTelemetry |
| Security | JWT, Guardrail, Audit Log |
| Frontend | Next.js 16, TypeScript |
| Testing | pytest, eval golden set |

---

## 빠른 시작

### 1. 백엔드

```bash
# 가상환경 생성
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 에 Neo4j / Qdrant / LLM / DART API 키 입력

# 서버 실행
uvicorn app.main:app --reload --port 8000
```

API 문서: `http://localhost:8000/docs`

### 2. 프론트엔드 (Next.js 대시보드)

```bash
cd frontend_app
npm install
npm run dev
```

### 3. 주요 엔드포인트

```
POST   /api/v1/analyze/start              # 분석 세션 시작 → thread_id 반환
GET    /api/v1/analyze/stream/{thread_id} # SSE 실시간 스트리밍
POST   /api/v1/analyze/interrupt/{thread_id} # 사용자 중단 요청
GET    /api/v1/analyze/state/{thread_id}  # 현재 에이전트 상태 조회
GET    /api/v1/analyze/metrics            # Prometheus 메트릭
GET    /api/v1/analyze/traces/{trace_id}  # OTel 분산 추적 스팬
```

---

## 환경변수 (.env.example)

```env
# Graph DB
NEO4J_URI=bolt+s://<your-neo4j-host>
NEO4J_USER=<your-neo4j-user>
NEO4J_PASSWORD=<your-neo4j-password>

# Vector DB
QDRANT_URL=https://<your-qdrant-host>
QDRANT_API_KEY=<your-qdrant-api-key>
QDRANT_COLLECTION=financial_docs

# LLM
LLM_BASE_URL=https://<provider-endpoint>/v1/chat/completions
LLM_API_KEY=<your-llm-api-key>
LLM_MODEL=<model-name>

# DART 공시 데이터 적재
DART_API_KEY=<your-dart-api-key>

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 테스트

```bash
pytest -q
python scripts/preflight_check.py
python scripts/audit_project.py
```

---

## 폴더 구조

```
.
├── app/
│   ├── agents/         # LangGraph 노드·그래프·스트리밍 버퍼
│   ├── api/            # FastAPI 엔드포인트 (SSE, interrupt, resume)
│   ├── memory/         # 에피소드·상태 저장소
│   ├── observability/  # Prometheus 메트릭, OTel 추적, 감사 로그
│   ├── retrieval/      # Neo4j + Qdrant 하이브리드 검색
│   └── security/       # JWT, 가드레일, sanitize
├── frontend_app/       # Next.js 16 대시보드
├── tests/              # pytest 회귀 테스트
├── scripts/            # preflight, audit, DART 데이터 적재
├── eval/               # 골든셋 평가
└── docker-compose.yml
```

---

*개발: 권지성 (Kwon Jiseong) · Soongsil Univ. Computer Science & Finance*
