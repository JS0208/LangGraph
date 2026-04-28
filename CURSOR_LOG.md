# CURSOR_LOG

## Sprint 6+ (Post-MVP — multi-entity / token stream / circuit / RAGAS-like / JWT / saver factory)

### 완료된 작업

- **GS-012 Multi-entity 분해** — `app/retrieval/real_clients.extract_companies(text)` 신설로 모든 alias 매치를 canonical 회사로 변환. `query_planner._heuristic_plan` 이 회사가 ≥2개 등장하면 회사별 sub_query 를 우선 분해. 골든셋 30/30 전체 통과 (pass_rate **100%**, intent **100%**, entity_recall **100%**, citation **100%**).
- **Circuit Breaker wiring** — `app/retrieval/query_router.py` 의 qdrant/neo4j 호출과 `app/llm/providers/openai_compat._post` 가 모두 모듈 레벨 `CircuitBreaker.acall` 로 감싸짐. 차단 상태에서 즉시 fallback 으로 회귀하며 `circuit_breaker_open_total` 메트릭을 계측한다. `tests/test_chaos_circuit.py` 로 chaos 검증 추가.
- **LLM 토큰 stream + SSE `token` 이벤트**
  - `LLMProvider.astream(...)` 추상 추가 — 기본은 complete 결과를 어절 단위로 yield.
  - `OpenAICompatProvider.astream(...)` — chat/completions `stream=true` SSE 디코딩(완전 구현). 실패 시 안전 fallback.
  - `MockProvider.astream(...)` — 결정론적 토큰 yield.
  - `LLMRouter.stream(intent, request)` — provider 실패 시 mock polyfill.
  - API `event_stream` 이 `orchestrator` / `generate_final_report` 노드의 최종 텍스트를 어절 단위 `{"type":"token", "node":..., "delta":...}` 로 progressive 송출.
  - 프론트엔드 `Executive Summary` 가 token delta 로 점진 업데이트되고 진행 중에는 커서가 깜박임.
- **RAGAS-like 자체 메트릭** — `eval/run_eval.py` 에 `context_recall`, `faithfulness`, `answer_relevance` (의존성 0 휴리스틱) 추가. JSON 결과·콘솔 모두 노출. fallback 환경에서 답변 텍스트가 짧아 점수가 낮은 것은 정상이며 (ragas 메트릭) 실 LLM 환경에서 재측정 시 의미를 가진다. CI 게이팅은 기존 `pass_rate` 만 사용.
- **JWT (HS256, 의존성 0)** — `app/security/jwt.py` 신설 (issue/verify, exp/iat/iss/sub, leeway). `app/security/auth.py` 에 `API_AUTH_MODE=jwt` + `API_AUTH_JWT_SECRET` + `API_AUTH_JWT_ISS` 모드 추가. `disabled / token / jwt` 3-mode dependency 로 운영 OAuth2 도입까지의 디딤돌.
- **PostgresSaver wire-compatible Saver Factory** — `app/memory/saver_factory.get_checkpointer(dsn)` 가 `langgraph.checkpoint.postgres.PostgresSaver`(우선) → `langgraph.checkpoint.sqlite.SqliteSaver` 순으로 시도하고 미설치 시 None. `_build_with_langgraph` 가 `get_checkpointer() or MemorySaver()` 로 자동 선택. `CHECKPOINTER_DSN=postgres://...` 또는 `sqlite:///...` 환경변수만으로 운영급 체크포인트 활성.

### 회귀 결과

| 지표 | 직전 (Sprint 6 1차) | 현재 |
|---|---|---|
| pytest | 105/105 | **126/126** |
| 골든셋 pass_rate | 96.67% | **100%** |
| intent_accuracy | 100% | 100% |
| entity_recall | 95.83% | **100%** |
| citation | 100% | 100% |
| audit_project | 19/19 | 19/19 |

### 자체 평가 & 잠재 리스크

- **RAGAS-like 메트릭 신뢰도**: 어절 등장 단순 비율 기반이라 fallback 환경에서는 항상 낮게 나온다. 실 LLM 환경에서 진짜 ragas 통합으로 교체 권장(별도 PR — `ragas` 의존성 도입).
- **PostgresSaver 도입**: import 실패 시 graceful fallback 만 검증했다. 실 PostgreSQL 인스턴스 연동은 docker-compose 의 `--profile real` 로 별도 검증 필요.
- **OpenAICompatProvider.astream**: 진짜 SSE token streaming 은 LLM 키 보유 환경에서만 검증 가능하다. 본 PR 의 단위 테스트는 mock fallback 경로만 결정론으로 검증.
- **JWT**: 자체 구현이지만 HS256 만 지원. RS256/ES256 또는 키 회전(JWKS)은 후속.

### 다음 행동 제안

1. **RAGAS 진짜 통합**: `requirements.txt` 에 `ragas`, `datasets` 추가 후 `eval/run_eval.py --ragas` 가 진짜 ragas pipeline 호출.
2. **OAuth2 Authorization Code + PKCE**: 외부 IdP 연동 (Keycloak/Auth0). JWT 검증은 그대로 활용 가능.
3. **OpenTelemetry**: `opentelemetry-instrumentation-fastapi` 도입 후 trace_id 가 자동 propagate 되도록.
4. **HITL Approval Gate**: `interrupt_requested` 가 발생하면 사용자 승인 후 `resume` 시 자동 진행되는 UX 보강.

---

## Sprint 4–6 (Memory · UX · Eval · Ops · Security)

### 완료된 작업

- **Sprint 4 — Memory · UX**
  - `app/memory/state_store.py` 신설: thread_id 별 GraphState 스냅샷 (in-memory + sqlite dual). `_InterruptRegistry` 로 thread-safe interrupt 신호 관리.
  - `app/memory/episode_store.py` 신설: 분석 종료 시 `(thread_id, query, intent, evidence_ids, finance_metrics, risk_points, duration_ms)` 영속화. RAGAS 후속 분석용.
  - `app/api/endpoints.py` 전면 재작성:
    - `POST /api/v1/analyze/start` — 가드레일 1차 차단 + `audit_event` 기록 + thread 발급.
    - `GET /api/v1/analyze/stream/{thread_id}` — **v1 페이로드와 v2 type 이벤트 동시 송출** (`stream_start`, `node_start`, `evidence_added`, `node_end`, `done`, `error`, `interrupt_requested`, 15s `ping`). 15s 무응답 ping/30s 노드 타임아웃 가드.
    - `POST /api/v1/analyze/interrupt/{thread_id}` — `StateStore.request_cancel` 로 진행 중 stream 코루틴에 신호.
    - `POST /api/v1/analyze/resume/{thread_id}` — 마지막 snapshot + state patch 재구성 후 `retrieve_context` 부터 재진입 + v2 송출.
    - `GET /api/v1/analyze/state/{thread_id}` — 마지막 snapshot 조회.
    - `GET /api/v1/analyze/episodes` — 최근 episode N건.
    - `GET /api/v1/analyze/health` / `GET /api/v1/analyze/metrics` — 헬스 + Prometheus text format.
  - 프론트엔드 강화:
    - `frontend_app/app/components/EvidenceDrawer.tsx` 신설: 우측 슬라이드 패널, evidence_id/source_type/company_name/preview 표시.
    - `frontend_app/app/components/KnowledgeGraph.tsx` 신설: 의존성 0 SVG 기반 KG live view (rooted radial layout + edges).
    - `frontend_app/app/page.tsx` 재작성: v2 이벤트(`evidence_added`/`node_start`/`node_end`/`interrupt_requested`/`done`/`error`/`ping`) 수용, v1 동작 100% 보존, **INTERRUPT 버튼**이 `/interrupt` 호출, 상단 navbar 에 intent · critic disagreement · evidence count 배지.
- **Sprint 5 — Eval · Ops**
  - `app/observability/metrics.py` 신설: 의존성 0 in-memory `MetricsRegistry` (counters + histograms) + Prometheus text exposition. snapshot/reset 지원.
  - `app/observability/logging.py` 신설: structlog 우선, 미설치 시 stdlib JSON formatter 로 회귀. `ContextVar` 기반 `trace_id` 컨텍스트.
  - `app/main.py` 재작성: `request_id_and_metrics` 미들웨어 — request_id 발급/주입, http_requests_total / http_request_duration_ms 자동 계측. CORS 화이트리스트 (`ALLOWED_ORIGINS`) 옵션.
  - `eval/golden_set/v0.json` **30문항으로 확장** (multi-entity, adversarial, alias, English, edge, M&A, ambiguous-year 등 18문항 추가).
  - `tests/test_golden_set_schema.py` 갱신: 30문항 floor 적용.
  - `.github/workflows/ci.yml` 신설: pytest + audit_project + golden eval JSON 게이팅 (pass_rate floor 0.75) + frontend ESLint 동시 실행. fallback 모드 강제 ENV.
- **Sprint 6 — Security · Reliability**
  - `app/security/guardrails.py` 신설: PII 마스킹(주민번호/카드/계좌/이메일) + prompt-injection 탐지 + out-of-scope hint + PII 입력 자동 차단(out_of_scope 분류).
  - `app/security/audit.py` 신설: append-only `AuditLog` (in-memory + sqlite WAL).
  - `app/security/auth.py` 신설: `API_AUTH_MODE=disabled|token` dev 토큰 dependency. `Bearer` / 평문 모두 수용. 미설정 시 데모/로컬 그대로 통과.
  - `app/utils/circuit.py` 신설: 의존성 0 `CircuitBreaker` (closed/open/half_open + 자동 회복 시간) + `CircuitOpenError`.
  - `app/retrieval/query_planner.py` 보강: `classify_input` 가드레일 1차 차단 → out_of_scope 분류 우선 적용.
- 신규 테스트: `test_memory.py`, `test_metrics.py`, `test_security.py`, `test_circuit.py`, `test_api_v2.py` — 35건 추가.
- 회귀 검증: `pytest -q` **105/105 그린**, `audit_project.py` 19/19 통과, `compileall` 통과, ESLint 정적 분석 0건.

### 측정 지표 (Sprint 5 베이스라인 — fallback)

| 지표 | Sprint 3 | Sprint 5 (현재) |
|---|---|---|
| pytest | 70/70 | **105/105** |
| 골든셋 | 12 | **30** |
| pass_rate | 83.33% | **96.67%** |
| intent_accuracy | 100% | 100% |
| entity_recall | 80% | **95.83%** |
| citation_attachment_rate | 100% | 100% |

### 자체 평가 & 잠재 리스크

- **PostgresSaver 미통합**: LangGraph 의 PostgresSaver/SqliteSaver 는 추가 의존성/마이그레이션 비용이 있어, 동등한 효과를 자체 `StateStore` 로 우선 제공. 운영 도입 시 `set_state_store(...)` 로 교체 가능.
- **Token-level streaming**: 현재 SSE v2 는 노드 단위 `node_start/node_end` + `evidence_added` 까지만 송출한다. 실 LLM 토큰 stream 은 LLM 공급자 토큰 stream 과 결합해 후속 PR.
- **Auth**: `API_AUTH_MODE=token` 은 dev 용. 운영 OAuth2/JWT 는 후속.
- **Multi-entity 비교 (GS-012)**: 단일 fail 의 원인은 query_planner 의 sub_query 분해가 두 번째 엔티티(SK하이닉스)를 채우지 못하기 때문. 향후 LLM planner 가 활성된 환경에서 자연스럽게 해결 예정 (휴리스틱 단계 분해 추가는 검토).
- **Circuit Breaker 적용 지점**: 자체 구현은 완료했으나, 실제 `real_clients` (Qdrant / Neo4j / OpenAI compat) 호출에 wiring 은 후속. 인터페이스(`acall`)는 즉시 사용 가능.
- **OTel/Grafana**: in-memory metrics 가 Prometheus text 호환이라 `prometheus.io/scrape` 어노테이션만으로 즉시 노출 가능. OTel collector 도입은 후속.

### 다음 행동 제안

1. LLM 토큰 stream 결합 (Sprint 4-C 잔여) — `LLMRouter.stream(...)` 인터페이스 + 노드 내부 yield-then-collect 패턴.
2. Circuit Breaker 를 `real_clients.qdrant_search`, `neo4j_run_cypher`, `openai_compat.invoke` 에 wiring (Sprint 6-B 마무리).
3. RAGAS 의존성 도입 후 `eval/run_eval.py` 에 faithfulness/answer_correctness 추가 (Sprint 5-D).
4. OAuth2/JWT 도입 + ACL middleware (Sprint 6-D).
5. Multi-entity 분해 휴리스틱 보강 (GS-012).

---

## Sprint 2–3 (Retrieval 2.0 + Agent Mesh)

### 완료된 작업

- **Sprint 2 (Retrieval 2.0 — 1차)**
  - `app/retrieval/cache.py` 신설: `InMemoryCache`(LRU+TTL) + `SqliteCache`(영속). 의존성 0.
  - `app/retrieval/query_planner.py` 신설: LLM 분해(가용 시) + 휴리스틱 fallback. 프롬프트 인젝션·범위 외 질의 차단.
  - `app/retrieval/cypher_safety.py` 신설: Cypher read-only 가드. DML/외부 procedure/허용외 라벨/관계 모두 차단.
  - `app/retrieval/query_router.py` 보강: `plan_query` 호출 → `Evidence.model_dump()` 누적 → 결과에 `plan`/`evidence` 키 추가. 기존 키 100% 보존.
- **Sprint 3 (Agent Mesh)**
  - `app/agents/nodes.py` 확장: `intent_classifier_node`, `critic_node`, `reflector_node` 추가. 기존 노드는 evidence_ids 자동 주입 + critic 점수 기반 라우팅으로 변경.
  - `app/agents/edges.py` 확장: `MAX_REFLEXIONS`, `VALID_NODES` 도입. `MAX_TURNS` 가드 유지.
  - `app/agents/graph.py` 재설계: `NODE_MAP` 기반 단일 진실, LangGraph/LocalFallback 양 경로에 신규 노드 등록.
  - `app/api/endpoints.py`, `app/main.py` 초기 state 가 `intent_classifier` 부터 시작하도록 갱신(하위호환 유지).
- 회귀 검증: `pytest -q` 70/70 그린, 신규 28건 추가 (`test_cache`, `test_query_planner`, `test_cypher_safety`, `test_query_router_v2`, `test_agent_mesh_v2`).

### 자체 평가 & 잠재 리스크

- **Hybrid Sparse / Reranker / Community Summary**: Sprint 2 의 1차 산출물에서 의도적으로 후순위로 미뤘다(외부 의존성/벤더 결정 필요). 인터페이스(`hybrid_retrieve`, `query_router`)는 이미 sub_query 기반으로 확장 가능하게 두었으므로, Sprint 5 실연동 검증과 함께 도입 예정.
- **Cypher Synthesis 호출 코드**: 가드(`cypher_safety.assert_safe`)는 도입했지만, 실제 LLM 합성 호출 코드는 아직 `real_clients.py` 의 고정 2-hop 쿼리만 사용한다. Sprint 5 운영 검증 단계에서 LLM 생성 Cypher → `assert_safe` → `neo4j.run` 흐름을 마무리한다.
- **Critic 휴리스틱**: 현재 critic 의 disagreement_score 는 단순 룰(인용 누락/모순/플래그) 기반이다. Sprint 5 의 골든셋 자동 평가 결과를 활용해 가중치를 보정한다.
- **테스트 커버리지**: 신규 노드 모두 단위 테스트 + LocalFallbackGraph 종단 테스트 2종을 통과한다.

### 다음 행동 제안

1. **Sprint 4 (Memory · UX)** 진입.
   - LangGraph `PostgresSaver` 통합(또는 dev 용 SQLite saver) + `app/memory/episode_store.py` 골격.
   - SSE v2 이벤트 (`type` 기반) 백엔드 구현 — v1 동시 송출.
   - 프론트엔드 3-pane 골격 + Live Knowledge Graph + Evidence Drawer.
2. **Sprint 5 (Eval · Ops)** 의 Eval 부분은 일찍 시작 가능:
   - `eval/run_eval.py` skeleton — 골든셋 v0 에 `hybrid_retrieve` 적중률(휴리스틱)을 먼저 측정.

---

## Sprint 0–1 (Upgrade Master Plan 착수)

### 완료된 작업

- 업그레이드 마스터플랜 `14_Upgrade_Master_Plan.md` 추가 — 7대 Pillar / 6 Sprint(12주) / KPI/리스크 명세.
- **Sprint 0 (Setup)**
  - `requirements.txt` 에 `tenacity`, `structlog`, `pytest-asyncio` 추가 (Sprint 2~6 후보는 주석으로 보존).
  - `Dockerfile`, `.dockerignore`, `docker-compose.yml` 추가 — `backend` 단독으로도 fallback 기동, `--profile real` 시 qdrant/neo4j/postgres/redis 동시 기동.
  - `eval/golden_set/v0.json` 12문항 + `eval/README.md` — Sprint 5 RAGAS 게이팅의 기준 데이터.
  - `4_Backend_API_and_SSE.md` 에 SSE v2 RFC 절(4.4) 추가 — v1 송출 그대로 유지하면서 `type` 기반 v2 이벤트 동시 송출 정의.
- **Sprint 1 (Foundations)**
  - `app/schemas.py` 신설 — Pydantic v2 모델 (`Evidence`, `FinanceMetrics`, `RiskPoint`, `CriticReport`, `SubQuery`, `QueryPlan`, `LLMUsage`, `TraceMeta`) 및 `STATE_SCHEMA_VERSION`.
  - `app/state.py` 확장 — `total=False` 로 변경, 신규 Optional 필드 추가(`schema_version`, `intent`, `query_plan`, `evidence`, `critic_report`, `disagreement_score`, `reflexion_count`, `trace_id`, `cost_usd`). 기존 호출자는 변경 없이 동작.
  - `app/utils/retry.py` 신설 — `tenacity` 우선, 미설치 환경 fallback 백오프. 5xx/429/네트워크 오류만 재시도.
  - `app/llm/` 패키지 신설 — `LLMRouter`, `LLMProvider` 추상화, `MockProvider`(결정론적), `OpenAICompatProvider`(현행 호출 호환).
  - `app/agents/llm_structured.py` 리팩터 — 직접 httpx 호출 제거, `LLMRouter.invoke(intent=...)` 위임. 기존 dict/list 출력 포맷 100% 보존.
  - 테스트 추가 — `test_schemas.py`, `test_retry.py`, `test_llm_router.py`, `test_golden_set_schema.py`, `test_llm_structured_router_integration.py` (총 24건). 기존 9건 모두 그린.
- 회귀 검증: `pytest -q` 33/33 그린, `compileall` 통과, `preflight_check.py` / `audit_project.py` 통과.

### 자체 평가 & 잠재 리스크

- **호환성**: `GraphState` 의 `total=False` 전환은 외부 코드가 키 누락을 가정하지 않는 한 안전하다. 현재 호출자 모두 `.get(...)` 방식이므로 영향 없음을 확인.
- **`os.environ` 영향**: `tests/conftest.py` 가 환경변수를 비우지만, `Settings` 가 import 시점 1회 평가되는 frozen dataclass 라 첫 import 후 `os.environ` 변경이 반영되지 않는다. Sprint 4 의 `Settings` 동적 리로드 도입 시 정리 예정.
- **Tenacity 의존성**: 미설치 환경 fallback 경로를 자체 테스트로 커버하지 못했음(현재는 설치된 환경에서 동작 확인). Sprint 2 도입 시 임포트 실패 시뮬레이션 테스트 추가 예정.
- **`OpenAICompatProvider`**: 현재는 `usage` 토큰 메타가 항상 0(현행 LLM 응답이 토큰 메타를 항상 채우지 않기 때문). Sprint 4 의 cost calculator 와 함께 채울 예정.

### 다음 행동 제안 (Next Action)

1. **Sprint 2 (Retrieval 2.0)** 진입.
   - `app/retrieval/cache.py` (임베딩 캐시, in-memory dict + sqlite fallback)
   - `app/retrieval/query_planner.py` (LLM 분해, 키 없을 때 휴리스틱 분해)
   - `app/retrieval/cypher_safety.py` (LLM 생성 Cypher 의 read-only 화이트리스트)
   - `query_router.py` 에 planner/evidence_ids 주입.
2. 골든셋 v0 자동 실행 하네스 stub 추가 (`eval/run_eval.py` skeleton, RAGAS 는 Sprint 5).

---

## 이전 기록 (정비 단계)

- 루트 `README.md`를 추가해 저장소 개요, 실행법, 환경 변수, 문서 인덱스를 정리했다.
- `frontend_app/README.md`, `frontend_prototype/README.md`를 실제 사용 방식에 맞게 교체했다.
- 설계 문서 `2_GraphRAG_Pipeline.md`, `3_LangGraph_Orchestration.md`, `4_Backend_API_and_SSE.md`, `5_Frontend_and_QA.md`의 깨진 경로와 오래된 설명을 최신 구현 기준으로 보정했다.
- 상태 문서 `6_Project_Status_and_Next_Steps.md`, `7_Progress_Dashboard.md`, `8_Runtime_Runbook.md`를 현재 워크스페이스 기준으로 재정렬했다.
- 루트 문서 파일명을 `번호_주제.md` 규칙으로 정리해 구조를 일관화했다.
- 실행 정합성 보강을 위해 의존성/환경 변수/검색 fallback 관련 코드와 문서를 함께 정리했다.
