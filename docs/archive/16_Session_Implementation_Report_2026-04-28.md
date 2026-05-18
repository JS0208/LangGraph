# 대화 세션 구현 보고서 (2026-04-28)

본 문서는 **이번 Cursor 대화 세션 전체**에서 수행한 작업을 **무엇(What)**, **왜(Why)**, **어떻게(How)** 관점에서 매우 구체적으로 정리한다.  
코드 경로·설계 결정·검증 수치·남은 과제까지 한 파일에서 재현 가능하도록 기술했다.

---

## 1. 배경과 세션 목표

### 1.1 사용자 요청의 흐름

1. **1차**: “현대 기준 최고 수준”에 맞게 프로그램 업그레이드 **기획안** 작성.
2. **2차 이후**: “차근차근 **모두 진행**” — 즉 기획안을 **실제 코드·테스트·운영 준비**까지 단계적으로 실행.

### 1.2 기술적 목표(북스타)

- **데모·오프라인 시연**: 외부 DB/LLM 키가 없어도 **fallback-first** 로 끝까지 동작.
- **실연동 확장**: 환경 변수만 채우면 Neo4j·Qdrant·실 LLM 경로가 활성화.
- **계약 유지**: 기존 API·SSE v1 스키마 **하위 호환**.
- **엔터프라이즈 준비**: 가드레일, 감사, 메트릭, CI 게이팅, 체크포인트 훅.

---

## 2. 무엇(What)을 했는가 — 영역별 요약

### 2.1 전략·문서

| 산출물 | 설명 |
|--------|------|
| `14_Upgrade_Master_Plan.md` | 7대 Pillar, 6 Sprint, KPI, 리스크를 담은 **마스터 플랜** (2026 SOTA GraphRAG DSS 방향). |
| `4_Backend_API_and_SSE.md` | **SSE v2 RFC** (type 기반 이벤트) — v1과 병행 가능 명시. |
| `CURSOR_LOG.md` | 스프린트별 변경·리스크·다음 액션 **연대기**. |
| `7_Progress_Dashboard.md` | 진행률·테스트 수·골든셋 메트릭 **대시보드**. |
| `6_Project_Status_and_Next_Steps.md` | 완료 vs 잔여 과제 **우선순위 정리**. |
| 본 문서 `16_Session_Implementation_Report_2026-04-28.md` | **세션 전체 서사** (What / Why / How). |

### 2.2 인프라·배포

| 산출물 | 설명 |
|--------|------|
| `Dockerfile` | FastAPI 백엔드 멀티스테이지 빌드, uvicorn 진입. |
| `docker-compose.yml` | backend 단독 실행 + `real`/`infra` 프로필로 Neo4j·Qdrant·Postgres·Redis 선택 기동. |
| `.dockerignore` | 빌드 컨텍스트 최적화·불필요 파일 제외. |
| `.github/workflows/ci.yml` | **pytest**, `audit_project.py`, **골든셋 eval** (pass_rate 게이팅), **프론트 eslint**. |

### 2.3 의존성

- `requirements.txt`: `tenacity`, `structlog`, `pytest-asyncio` 등 스프린트 1~3에 필요한 패키지 반영 (일부 후속은 주석으로만 제안).

### 2.4 핵심 백엔드 아키텍처

| 영역 | 주요 모듈 | 역할 |
|------|-----------|------|
| 스키마 | `app/schemas.py` | Pydantic v2 — Evidence, QueryPlan, FinanceMetrics 등 + `from_legacy` 어댑터. |
| 상태 | `app/state.py` | `GraphState` TypedDict `total=False` + intent, evidence, critic, trace 등 **선택 필드** 확장. |
| 재시도 | `app/utils/retry.py` | `tenacity` 우선, 미설치 시 지수 백오프 **fallback**. |
| 회로 차단 | `app/utils/circuit.py` | closed/open/half_open, **의존성 0**. |
| LLM 레이어 | `app/llm/` | `OpenAICompatProvider`, `MockProvider`, **`LLMRouter`**, **`astream`/`stream`**. |
| LLM 호출 일원화 | `app/agents/llm_structured.py` | httpx 직접 호출 제거, **Router 위임**. |
| 검색 | `app/retrieval/cache.py` | InMemory + Sqlite 캐시. |
| 검색 | `app/retrieval/query_planner.py` | LLM 분해(가용 시) + **휴리스틱 분해** + 가드레일 연동. |
| 검색 | `app/retrieval/cypher_safety.py` | 읽기 전용·허용 라벨/관계 **Cypher 가드** (관계 타입 오인식 버그 수정 포함). |
| 검색 | `app/retrieval/query_router.py` | planner 연동, **evidence/plan** 주입, **CircuitBreaker** 로 실 검색 래핑. |
| 검색 | `app/retrieval/real_clients.py` | `extract_company_year`, **`extract_companies`** (멀티 엔티티). |
| 에이전트 | `app/agents/nodes.py` | intent_classifier, critic, reflector + 기존 노드 **evidence_ids·불일치 점수** 연동. |
| 에이전트 | `app/agents/edges.py` | MAX_REFLEXION, disagreement 기반 **라우팅**. |
| 에이전트 | `app/agents/graph.py` | LocalFallback + LangGraph 경로 동기화, **`get_checkpointer()`** 주입. |
| API | `app/api/endpoints.py` | start/stream/interrupt/resume/state/episodes/**metrics**, **SSE v1+v2 동시**, **token** progressive. |
| 앱 진입 | `app/main.py` | CORS 화이트리스트, **request_id + HTTP 메트릭** 미들웨어. |
| 메모리 | `app/memory/state_store.py` | thread별 스냅샷 + **interrupt 레지스트리**. |
| 메모리 | `app/memory/episode_store.py` | 분석 종료 **episode** 아카이브. |
| 메모리 | `app/memory/saver_factory.py` | PostgresSaver / SqliteSaver **가능 시** LangGraph checkpointer. |
| 관측 | `app/observability/metrics.py` | in-memory 카운터·히스토그램, **Prometheus text**. |
| 관측 | `app/observability/logging.py` | structlog 우선, 미설치 시 **JSON stdlib** fallback, trace ContextVar. |
| 보안 | `app/security/guardrails.py` | PII 마스킹, prompt injection·OOS 힌트, **PII 입력 out_of_scope**. |
| 보안 | `app/security/audit.py` | append-only 감사 로그 (sqlite 옵션). |
| 보안 | `app/security/auth.py` | `disabled` / `token` / **`jwt`**. |
| 보안 | `app/security/jwt.py` | **HS256 자체 구현** (PyJWT 불필요), exp/iss/leeway. |

### 2.5 평가

| 산출물 | 설명 |
|--------|------|
| `eval/golden_set/v0.json` | **30문항** 골든셋 (facts/risk/trend/relation/adversarial/PII 등). |
| `eval/run_eval.py` | fallback 강제 옵션, 휴리스틱 메트릭 + **RAGAS-like** (의존성 0) 3지표, `--json`. |
| `eval/README.md` | 골든셋 구조·목적. |

### 2.6 프론트엔드

| 산출물 | 설명 |
|--------|------|
| `frontend_app/app/components/EvidenceDrawer.tsx` | 근거 **슬라이드 패널**. |
| `frontend_app/app/components/KnowledgeGraph.tsx` | **SVG** 라이브 KG 뷰 (의존성 0). |
| `frontend_app/app/page.tsx` | v2 이벤트 수용, interrupt, intent/critic 배지, **token progressive 요약**. |

### 2.7 테스트

- `tests/test_*.py` 다수: 스키마, retry, router, cache, planner, cypher, query_router v2, agent mesh v2, memory, metrics, security, circuit, chaos, api v2, llm_stream, jwt, saver_factory, golden_set 스키마 등.
- **세션 종료 시점 기준**: **126 passed** (로컬 실행 기준).

---

## 3. 왜(Why) 그렇게 했는가 — 설계 원칙

### 3.1 Fallback-first

**이유**: PoC·데모·CI는 외부 키·DB 없이 **결정론**이어야 재현성과 게이팅이 가능함.  
**결과**: `run_eval.py`·CI에서 env를 비우고 LocalFallbackGraph + mock 경로로 측정.

### 3.2 하위 호환 (Breaking change 최소화)

**이유**: 기존 프론트·문서·통합이 v1 SSE·dict state에 의존.  
**결과**: SSE에 **v1 JSON 페이로드 유지** + v2 `type` 이벤트 **병행**; `GraphState`는 `total=False`.

### 3.3 관심사 분리

**이유**: LLM·검색·라우팅·보안을 한 파일에 두면 유지보수·테스트가 붕괴.  
**결과**: `app/llm`, `app/retrieval`, `app/security`, `app/memory`, `app/observability` 패키지화.

### 3.4 이중 방어 (Guardrails + Planner)

**이유**: API 레이어와 planner 레이어 모두에서 **prompt injection·OOS·PII**를 걸러야 오탐/미탐 균형이 잡힘.  
**결과**: `start` 엔드포인트 1차 차단 + `query_planner`의 `_classify_intent`가 `classify_input` 우선.

### 3.5 운영 관측 가능성

**이유**: “최고 수준” 제품은 장애 시 **원인 추적**과 **SLO**가 전제.  
**결과**: 구조화 로그, `/metrics` Prometheus 텍스트, HTTP 지연·에러 카운터, 회로 차단 카운터.

### 3.6 의존성 0 옵션 유지

**이유**: 엔터프라이즈 승인 전에는 PyPI 패키지 추가가 느림.  
**결과**: JWT·CircuitBreaker·in-memory metrics·RAGAS-like 휴리스틱을 **표준 라이브러리+기존 스택**으로 구현.

---

## 4. 어떻게(How) 구현했는가 — 기술적 세부

### 4.1 Query Planner와 멀티 엔티티 (GS-012)

**문제**: “삼성전자와 SK하이닉스 비교” 같은 질의에서 **첫 회사만** sub_query에 잡히면 entity_recall이 깨짐.  

**방법**:
1. `COMPANY_ALIAS_MAP` 기반으로 질의 문자열에서 **모든 매칭 alias**를 canonical로 수집하는 `extract_companies()` 추가 (`app/retrieval/real_clients.py`).
2. 휴리스틱 플래너에서 `len(companies) >= 2`이면 **회사당 하나의 SubQuery** 생성 (`app/retrieval/query_planner.py`).

**효과**: fallback 모드에서도 골든셋 **entity_recall 100%** 달성.

### 4.2 Circuit Breaker

**문제**: 외부 Qdrant/Neo4j/LLM이 연속 실패할 때 **대기·비용 폭증**.  

**방법**:
- `query_router._run_real_retrieval`에서 `qdrant_search`·`neo4j_two_hop`를 각각 `QDRANT_BREAKER` / `NEO4J_BREAKER`로 감쌈.
- `OpenAICompatProvider`는 내부 `_breaker`로 `_post` 감쌈; open 시 RuntimeError → 상위 Router가 mock으로 폴백 가능.
- `tests/test_chaos_circuit.py`로 반복 실패 시 open 전이·fallback·메트릭 스모크 검증.

### 4.3 토큰 스트리밍 (SSE v2 `token`)

**문제**: UX 측면에서 **최종 요약**이 한 번에 뿌려지면 “에이전트가 생각 중” 느낌이 약함.  

**방법**:
1. `LLMProvider.astream` 기본 구현 = `complete` 결과를 어절 단위 yield.
2. `OpenAICompatProvider.astream` = OpenAI 호환 API에 `stream: true`, SSE 라인 파싱.
3. `LLMRouter.stream` = 실패 시 mock으로 polyfill.
4. `endpoints.stream`에서 `orchestrator` / `generate_final_report` 노드 이후 **요약 텍스트**를 `_split_tokens`로 chunk 송출.
5. 프론트 `streamingText` 상태로 Executive Summary **progressive 렌더**.

**한계(명시)**: 노드 내부 LLM이 아직 “진짜 스트리밍으로 중간 상태 갱신”까지는 아니고, **노드 출력 확정 후** 토큰 분할 송출 + OpenAI stream은 Router 레벨에서 소비 가능. 이후 단계는 노드 내부에서 generator 패턴으로 확장 가능.

### 4.4 RAGAS-like 자체 메트릭

**문제**: `ragas` 패키지 의존 없이도 ** trends / 회귀 감지**용 숫자가 필요.  

**방법** (`eval/run_eval.py`):
- `context_recall`: evidence 텍스트에 **expected_keywords** 등장 비율.
- `faithfulness`: 답변의 긴 어절이 evidence에 등장하는 비율 (휴리스틱).
- `answer_relevance`: 답변이 키워드에 얼마나 맞는지.

**주의**: fallback/mock 환경에서는 텍스트가 짧아 **지표가 낮게** 나오는 것이 정상. CI 게이팅은 기존 `pass_rate` 중심 유지.

### 4.5 JWT 인증 모드

**문제**: 데모는 열려 있어야 하고, 스테이징은 **Bearer 검증**이 필요.  

**방법**:
- `API_AUTH_MODE=jwt` + `API_AUTH_JWT_SECRET` (+ 선택 `API_AUTH_JWT_ISS`).
- HS256 HMAC, `issue_token`/`verify_token` 자체 구현으로 **의존성 0**.

### 4.6 LangGraph Checkpointer 팩토리

**문제**: 운영은 Postgres, 로컬은 Sqlite가 적합.  

**방법**:
- `get_checkpointer()`가 `CHECKPOINTER_DSN`으로 Postgres / Sqlite saver를 **importlib로 시도**, 실패 시 None.
- `_build_with_langgraph`는 `get_checkpointer() or MemorySaver()`.

### 4.7 Cypher Safety 라벨/관계 혼동 버그

**문제**: `[:HAS_REPORT]` 같은 관계 타입이 **노드 라벨**로 오인식되어 안전 쿼리가 거절됨.  

**방법**: 관계 블록을 먼저 제거한 뒤 라벨 추출 (`cypher_safety.py`).

### 4.8 Windows 콘솔 인코딩

**문제**: `run_eval.py`의 이모지 출력이 cp949에서 깨짐.  

**방법**: `[PASS]` / `[FAIL]` 같은 ASCII 마커로 교체.

---

## 5. 검증 결과 (세션 기준)

| 항목 | 값 |
|------|-----|
| pytest | **126 passed** (세션 후보 기준) |
| 골든셋 (30문항, fallback) | pass_rate **100%**, intent **100%**, entity **100%**, citation **100%** |
| `scripts/audit_project.py` | 19/19 통과 |
| RAGAS-like (fallback) | 낮은 값 정상 (실연동에서 재해석) |

---

## 6. 남은 과제 (문서화된 다음 스텝)

1. **진짜 RAGAS** 패키지 통합 + CI 임계 재조정.
2. **OpenTelemetry** + 분산 트레이싱.
3. **OAuth2 Authorization Code (PKCE)** + 외부 IdP.
4. **노드 내부**에서 LLM 스트림을 상태에 반영하는 **true streaming**.
5. Hybrid sparse / Reranker / Community summary 등 Retrieval 2.0 후속.

---

## 7. 환경 변수 빠른 참조

| 변수 | 용도 |
|------|------|
| `NEO4J_*`, `QDRANT_*`, `LLM_*` | 실연동 검색·LLM |
| `ALLOWED_ORIGINS` | CORS 화이트리스트 |
| `API_AUTH_MODE` | `disabled` / `token` / `jwt` |
| `API_AUTH_TOKENS` | 토큰 화이트리스트 (콤마) |
| `API_AUTH_JWT_SECRET`, `API_AUTH_JWT_ISS` | JWT 검증 |
| `CHECKPOINTER_DSN` | Postgres 또는 Sqlite LangGraph saver |

---

## 8. 결론

이번 세션은 **기획(`14_Upgrade_Master_Plan.md`)을 실행 계획으로 바꾼 뒤**, **스키마·LLM·검색·에이전트·API·메모리·보안·관측·평가·CI·프론트**를 한 줄기로 묶어 **fallback 유지 + 실연동 확장 + 계약 보존**이라는 세 가지 제약을 동시에 만족하도록 구현했다.  

그 결과 **테스트·감사 스크립트·골든셋**이 동시에 녹색이 되는 **재현 가능한 품질 게이트**를 갖추었고, 남은 작업은 주로 **외부 의존 패키지·인프라·true streaming**으로 명확히 이관되었다.

---

*작성: Cursor Agent 세션 종료 시점 기준. 커밋 해시는 저장소의 해당 커밋을 참조.*
