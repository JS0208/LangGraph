# 14. Upgrade Master Plan — "2026 SOTA Enterprise GraphRAG DSS"

> 본 문서는 현재 GraphRAG 다중 에이전트 데모(`README.md`, `0_System_Context.md` ~ `13_Selected_Ingestion_Checklist.md` 기준)를 **"현대(2026) 엔터프라이즈에서 최고 수준의 금융 의사결정 지원 시스템"** 으로 격상시키기 위한 단일 기획서다.
>
> 본 문서는 **What/Why/How/When/How-to-verify** 다섯 축을 모두 포함하며, 모든 항목은 현재 저장소의 파일 경로/모듈에 직접 매핑된다. 문서 번호 체계(0~13)와 충돌하지 않도록 14번을 부여했다.

---

## 0. Executive Summary (한 페이지 요약)

### 0.1 한 문장 정의
> *"DART 기반 5대 IT 기업 데이터를 GraphRAG로 이중 인덱싱하고, 근거(Evidence)에 묶인 다중 에이전트가 토론·검증·합의하는 과정을, 모든 단계가 추적·평가·재현 가능한 형태로 실시간 스트리밍하는 엔터프라이즈급 의사결정 엔진을 만든다."*

### 0.2 What Changes (As-Is → To-Be 한 줄 요약)

| 축 | 현재(As-Is) | 목표(To-Be, 2026 SOTA) |
|---|---|---|
| 검색 | dense-only Qdrant + 1회성 2-hop Cypher | **Hybrid(BM25 + dense + reranker) + Multi-hop Graph Walk + Community Summary + Query Decomposition** |
| 에이전트 | 3-노드 단방향(Finance→Risk→Orchestrator) | **Planner / Retriever / Finance / Risk / Critic / Orchestrator + Reflexion + HITL** |
| 토론 | turn_count<=3, 자동 합의 | **Evidence-grounded Debate + Disagreement Score + 강제 재검색 루프** |
| 근거 | `messages`에 자유서술 | **모든 결론에 chunk_id / node_id / Cypher path 인용 (citation graph)** |
| 메모리 | 단발성 in-memory | **LangGraph Checkpointer(Postgres) + Long-term Vector Memory + Thread Resume** |
| LLM | 단일 모델 직호출(httpx) | **Model Router(추론용/요약용/판단용 분리) + Semantic Cache + Token Budgeting** |
| 평가 | 단순 pytest 4건 | **RAGAS + 골든셋 + 적대적 시나리오 + LangSmith Trace + CI 게이팅** |
| 운영 | uvicorn + .env | **Docker Compose / Helm + OTel Trace + Prom/Grafana + GitHub Actions CD** |
| 보안 | CORS=`*`, 키 평문 | **OAuth2/JWT + Secrets Vault + PII Mask + Prompt Injection Guardrails + Audit Log** |
| UX | Log 패널 + 카드 | **Token streaming + Live Knowledge Graph(Cytoscape) + Evidence Drawer + Debate Timeline + HITL 개입 UI** |

### 0.3 Why Now
- 2026년 GraphRAG는 Microsoft, Neo4j, LlamaIndex 등 주요 벤더의 표준 패턴으로 자리 잡았고, "Hybrid Retrieval + Reranker + Citation"이 엔터프라이즈 도입 최소선임.
- LangGraph 0.2+의 Checkpointer/Subgraph/Interrupt API가 안정화되어 진정한 stateful·HITL 워크플로우 구현 비용이 급감했다.
- 평가 가능성(RAGAS, LangSmith) 없이는 환각 통제를 입증할 수 없고, 입증 없이는 금융권 도입이 불가하다.

### 0.4 Success Criteria (단 4줄)
1. **정확성**: 골든셋 30문항에서 RAGAS faithfulness ≥ 0.85, answer_correctness ≥ 0.80
2. **속도**: TTFU(Time-To-First-Update) p95 ≤ 1.5s, end-to-end p95 ≤ 20s
3. **신뢰성**: 모든 결론 100% citation-grounded, 환각 의심률 ≤ 5%
4. **운영성**: 단일 명령(`make up` / `docker compose up`)으로 fallback·real 양쪽 재현, CI 그린 시 자동 배포 가능

---

## 1. As-Is 정밀 진단 (Gap Analysis)

### 1.1 현재 자산(강점)
- `app/agents/graph.py`: `langgraph` 미설치 환경에서도 `LocalFallbackGraph`로 동등 흐름 보장 → **재현성** 확보됨.
- `app/retrieval/query_router.py`: Qdrant 실패 시 scroll fallback, Neo4j 실패 시 seed로 자동 전환 → **fallback-first 철학** 일관됨.
- `app/agents/llm_structured.py`: 429 재시도 + JSON-only 강제 + `has_real_llm` 분기 → **방어적 LLM 호출 패턴** 정착.
- `app/api/endpoints.py`: SSE + `asyncio.wait_for(30s)` + 예외 시 fallback 이벤트 → **스트리밍 안정화** 됨.
- `frontend_app/app/page.tsx`: 노드별 카드, consensus 배지, 그래프 노드/엣지 태그 표기 → **UX 기본기** 확립.

### 1.2 갭(약점) — 7대 카테고리 38개 항목

#### A. Retrieval 한계
- A1. dense 임베딩 단일 채널(BM25/sparse 미사용) → 한국어 고유명사·숫자 회수율 낮음
- A2. reranker 부재 → 상위 5건 정밀도 한계
- A3. query decomposition 부재 → "카카오의 자회사 카카오게임즈의 규제 리스크가 본사에 미치는 영향" 같은 multi-hop 질의를 단일 검색으로 처리
- A4. Neo4j 쿼리가 고정 2-hop, LLM 기반 Cypher 생성 없음 → 임의 그래프 추론 불가
- A5. community summary / hierarchical RAG 없음 (Microsoft GraphRAG 핵심 누락)
- A6. 캐시(임베딩 캐시·답변 캐시) 부재
- A7. payload index가 ingestion 시점에 1회성으로만 보장됨

#### B. Multi-Agent 한계
- B1. 토론 자체가 없음(현 코드는 직선 파이프라인). `consensus_reached`는 `has_fin and has_risk`로 사실상 항상 True
- B2. critic·verifier·planner 부재
- B3. 도구 호출(tool calling) 일반화 없음 — 검색 1회만 가능
- B4. self-reflection / re-plan 루프 없음
- B5. 질의 의도 분류(intent classification) 없음 → 비-금융 질의에도 같은 파이프라인 강제

#### C. State & Memory 한계
- C1. `MemorySaver`는 프로세스 재시작 시 휘발 → thread resume 불가
- C2. 사용자/조직 단위 long-term memory 없음
- C3. 직전 세션 결과 재활용 불가(반복 질의 비용 낭비)
- C4. State 스키마 버저닝 없음

#### D. Evaluation/Observability 한계
- D1. RAGAS 미연결 — 환각률 정량화 불가
- D2. 골든셋(Golden Set) 부재 — 회귀 비교 기준 없음
- D3. LangSmith / OpenTelemetry trace 없음
- D4. 토큰·비용 트래킹 없음
- D5. 적대적(jailbreak·PII inject) 시나리오 검증 없음
- D6. p95 latency / TTFU SLO 측정 없음

#### E. Reliability 한계
- E1. 회로차단기(circuit breaker) 부재 — 외부 장애가 SSE를 30s 점유
- E2. 임베딩 호출이 점별(per-item) 직렬 처리 → 적재 시간 폭증
- E3. 재시도 정책이 함수마다 상이(2.5^n + jitter vs 2^n) → 일관성 없음
- E4. 종료 신호(graceful shutdown) 처리 없음
- E5. SSE keep-alive ping 없음 → 프록시 환경에서 끊김

#### F. Security 한계
- F1. `CORSMiddleware allow_origins=["*"]` 운영 노출 시 위험
- F2. 인증·인가 전무 — 누구나 `/api/v1/analyze/start` 호출 가능
- F3. 시크릿이 `.env` 파일 평문에만 의존
- F4. 프롬프트 인젝션 가드(입력 sanitize) 없음
- F5. LLM 응답 가드(toxic/PII filter) 없음
- F6. 감사 로그(audit log) 없음

#### G. UX/Frontend 한계
- G1. 토큰 단위 스트리밍 없음(노드 단위만 표시)
- G2. Knowledge Graph 시각화가 단순 태그 — 노드/엣지 그래프 뷰 없음
- G3. 근거(chunk·disclosure) drawer 없음
- G4. HITL 개입 UI 없음(에이전트 멈춤·수정·재개 불가)
- G5. 다국어/접근성(WCAG AA) 검증 없음
- G6. 모바일 반응형 미흡

---

## 2. North Star — 최고 수준의 정의

### 2.1 5대 비기능 요구(NFR) — "이 수준이면 글로벌 최상위"

| NFR | 임계값 | 측정 방법 |
|---|---|---|
| **정확성(Faithfulness)** | RAGAS faithfulness ≥ 0.85 | 골든셋 30문항/주 |
| **응답성(Responsiveness)** | TTFU p95 ≤ 1.5s, E2E p95 ≤ 20s | OTel histogram |
| **추적성(Traceability)** | 결론 100%가 인용 가능한 chunk·node ID 보유 | citation 검증 lint |
| **회복력(Resilience)** | 외부 의존 1개 단절 시 fallback 성공률 ≥ 99% | chaos test |
| **운영성(Operability)** | 1명이 한 명령으로 dev/staging 재현 | `make up`, `docker compose up` |

### 2.2 정성적 비전
> "사용자는 한 줄의 질문을 던진다. 1.5초 안에 첫 사고 과정이 흐르고, 에이전트가 서로 다른 의견을 내고, 비판자가 근거를 요구하고, 추가 검색이 일어나고, 합의가 형성되고, 모든 결론에 클릭 가능한 출처가 달린다. 사용자는 언제든 멈추고 변수를 바꿔 재개할 수 있다. 운영자는 모든 토큰·비용·지연·실패를 그래프로 본다."

---

## 3. 7대 업그레이드 Pillar — 상세 설계

### Pillar 1. Retrieval 2.0 — Hybrid · Hierarchical · Graph-Native

#### 1.1 변경 대상 파일
- `app/retrieval/query_router.py` (개편)
- `app/retrieval/real_clients.py` (개편)
- 신규: `app/retrieval/hybrid_search.py`, `app/retrieval/reranker.py`, `app/retrieval/query_planner.py`, `app/retrieval/cypher_synth.py`, `app/retrieval/community_summary.py`, `app/retrieval/cache.py`

#### 1.2 핵심 설계
1. **Query Planner (LLM)**: 질의를 sub-query 1~5개로 분해(decomposition). 각 sub-query에 대해 (a) 대상 엔티티, (b) 시간 범위, (c) 검색 의도(facts/relation/trend) 태깅.
2. **Hybrid Search**:
   - dense: Qdrant `gemini-embedding-001` (현행 유지)
   - sparse/BM25: Qdrant 1.10+ `sparse vectors` 또는 OpenSearch BM25 사이드카
   - 가중 합산(α·dense + (1-α)·sparse), α는 질의 의도에 따라 동적 조정
3. **Reranker**: BGE-reranker-v2 또는 Cohere Rerank 3 호출 → 상위 K=20 → 5로 압축
4. **Graph Query Synthesis**:
   - LLM이 자연어 → Cypher 생성(safe-list 노드 라벨/관계만 허용)
   - guard: read-only 키워드 화이트리스트(MATCH/RETURN/WITH/UNWIND), DML 금지
5. **Community Summary**:
   - 적재 단계에서 Leiden/Louvain으로 커뮤니티 검출 → 커뮤니티별 LLM 요약을 별도 collection에 저장
   - Multi-hop 질의 시 community summary 우선 → drill-down
6. **Citation Graph**: 모든 hit에 `evidence_id`(chunk_id 또는 graph node_id) 부여, downstream 노드에서 의무 인용
7. **Caching**:
   - 임베딩 캐시: SHA256(query) → vector, Redis(또는 sqlite fallback)
   - 답변 캐시: semantic cache (cosine ≥ 0.97 hit)

#### 1.3 인터페이스(요약)
```python
# app/retrieval/query_planner.py
async def plan_query(user_query: str) -> QueryPlan: ...
# QueryPlan = list[SubQuery(intent, entity, year_range, weight)]

# app/retrieval/hybrid_search.py
async def hybrid_search(sub: SubQuery, k: int = 20) -> list[Hit]: ...

# app/retrieval/reranker.py
async def rerank(query: str, hits: list[Hit], top_k: int = 5) -> list[Hit]: ...

# app/retrieval/cypher_synth.py
async def synthesize_cypher(sub: SubQuery) -> SafeCypher: ...

# app/retrieval/query_router.py
async def hybrid_retrieve(user_query, *, company, year) -> AnalysisContext:
    plan = await plan_query(user_query)
    raw_hits = await asyncio.gather(*[hybrid_search(s) for s in plan])
    reranked = await rerank(user_query, flatten(raw_hits))
    graph = await execute_safe_cypher(synth(plan))
    return build_analysis_context(reranked, graph, plan)
```

#### 1.4 검증 기준
- 골든셋 multi-hop 질의 5건에서 회수율(recall@5) ≥ 0.9
- 캐시 적중률 ≥ 30% (반복 질의 워크로드 기준)
- p95 retrieval latency ≤ 1.2s

---

### Pillar 2. Agent Mesh 2.0 — Planner · Critic · Reflexion · HITL

#### 2.1 변경 대상 파일
- `app/agents/nodes.py`, `app/agents/edges.py`, `app/agents/graph.py` (개편)
- `app/state.py` (확장)
- 신규: `app/agents/planner.py`, `app/agents/retriever.py`, `app/agents/critic.py`, `app/agents/reflector.py`, `app/agents/tools.py`, `app/agents/prompts/`

#### 2.2 새 에이전트 토폴로지
```
START → intent_classifier
        ├─(out_of_scope)→ refuse_node → END
        └─(in_scope)→ planner
                       └→ retriever ←──────────────┐
                            └→ finance_analyst     │
                            └→ risk_compliance     │
                                  └→ critic ───────┤ (요청 시 재검색)
                                       └→ orchestrator
                                            ├─(consensus)→ generate_final_report → END
                                            └─(disagree, turn<MAX)→ reflector → planner
```

#### 2.3 각 노드 책무
- **intent_classifier**: domain in/out 분기 + 질의 유형(facts/relation/trend/risk) 태깅
- **planner**: `QueryPlan` 산출 + 필요한 도구 목록 결정
- **retriever**: Pillar 1의 hybrid_retrieve 호출, evidence 누적
- **finance_analyst / risk_compliance**: 인용 강제(JSON 스키마에 `evidence_ids: list[str]` 필수)
- **critic**: 두 분석가 출력의 (a) 인용 누락, (b) 수치 모순, (c) 일반론 남용을 점수화 → `disagreement_score`
- **reflector**: critic 결과를 받아 추가 검색 쿼리 또는 가설 생성
- **orchestrator**: critic 점수 기반으로만 합의 선언

#### 2.4 GraphState 확장 (after-image)
```python
class GraphState(TypedDict):
    user_query: str
    target_company: str | None
    target_year: int | None

    # 새 필드
    intent: Literal["facts", "relation", "trend", "risk", "out_of_scope"]
    query_plan: list[SubQuery]
    evidence: Annotated[list[Evidence], operator.add]   # citation pool
    finance_metrics: FinanceMetrics                     # Pydantic model
    risk_points: list[RiskPoint]                        # Pydantic model
    critic_report: CriticReport | None
    disagreement_score: float                           # 0~1, ≤0.2 → consensus
    reflexion_count: int                                # 별도 카운터
    # 기존 필드
    messages: Annotated[list[Message], operator.add]
    turn_count: int
    consensus_reached: bool
    next_node: str
    # 운영 필드
    trace_id: str
    started_at: datetime
    cost_usd: float
```

#### 2.5 라우팅 규칙(원자적)
- `MAX_TURNS=4`, `MAX_REFLEXIONS=2`, `disagreement_score ≤ 0.2` 일 때 합의
- 회로차단: `cost_usd > BUDGET` 또는 `elapsed > 60s` → 강제 final_report

#### 2.6 도구(tool calling) 표준화
모든 외부 호출은 `app/agents/tools.py`의 단일 인터페이스를 거친다. (semantic_search, graph_query, calculator, dart_lookup, web_search-옵션)

```python
@tool("semantic_search")
async def semantic_search(query: str, k: int = 5, filter: dict | None = None) -> list[Hit]: ...
```

#### 2.7 검증 기준
- 골든 시나리오 A(자회사 리스크 전이)에서 critic이 최소 1회 재검색 트리거
- 시나리오 B(상충 데이터)에서 turn_count = MAX_TURNS 도달 시 명시적 "합의 실패" 결론
- evidence_ids 미부착 응답 0건

---

### Pillar 3. Memory & State — Stateful, Resumable, Versioned

#### 3.1 변경 대상
- `app/agents/graph.py`: `MemorySaver` → `PostgresSaver`(또는 SQLite for dev)
- 신규: `app/memory/long_term.py`, `app/memory/episode_store.py`, `migrations/`

#### 3.2 설계
1. **Short-term**: LangGraph `PostgresSaver` (thread_id별 상태 보존, 재시작 안전)
2. **Episode Store**: 매 분석 종료 시 (질의, 결론, evidence, score)를 archive 테이블에 적재
3. **Long-term Vector Memory**: Qdrant 별도 collection `user_memory_{user_id}` (요약 + 메타)
4. **Schema Versioning**: `app/state.py`에 `STATE_SCHEMA_VERSION`, 로드 시 마이그레이터로 자동 변환
5. **Resume API**: `POST /api/v1/analyze/resume/{thread_id}` — interrupt 후 재개

#### 3.3 검증 기준
- 서버 재기동 후에도 `thread_id`로 동일 결과 재현
- `episode_store` 30일치 적재 후 retrieval에서 "이전에 분석했던 회사" 신호 활용

---

### Pillar 4. LLM Layer — Router · Cache · Budget · Guardrail

#### 4.1 변경 대상
- `app/agents/llm_structured.py` (개편)
- 신규: `app/llm/router.py`, `app/llm/cache.py`, `app/llm/budget.py`, `app/llm/guardrail.py`, `app/llm/providers/`

#### 4.2 설계
1. **Model Router**:
   - 추론(reasoning) 모델: 큰 모델 (Gemini 2.5 Pro / Claude 3.5 Sonnet 급) — orchestrator·critic·planner
   - 추출(extraction) 모델: 작고 빠른 모델 — finance/risk JSON 추출
   - 임베딩: `gemini-embedding-001` 유지 + fallback `text-embedding-3-small`
2. **Provider 추상화**: `LLMProvider` 인터페이스(complete/stream/embed) + Gemini/Anthropic/OpenAI 구현 + Mock
3. **Semantic Cache**: 입력 임베딩 코사인 ≥ 0.97 → 동일 응답 반환
4. **Budget**:
   - 요청별 max_tokens 강제
   - 누적 cost 추적, 임계 초과 시 회로차단
5. **Guardrails**:
   - Input: prompt-injection 패턴 감지(allowlist + heuristic)
   - Output: PII 마스킹, 금융 부적격 권유 금지(rule-based + LLM judge), JSON 스키마 강제

#### 4.3 호출 정책
- 통일된 재시도: `tenacity` — exponential backoff(2^n) + ±20% jitter, 최대 3회, 5xx/429만 재시도
- 타임아웃: provider별 분리(reasoning 60s / extraction 20s / embed 10s)
- 모든 호출은 `LLMRouter.invoke(intent=...)` 단일 진입점 통과 — 메타(usage·latency·model_id)를 OTel span에 기록

#### 4.4 검증 기준
- 동일 질의 100회 시 적중률 ≥ 95% 캐시
- p95 reasoning latency ≤ 8s
- guardrail로 prompt-injection 30종 차단율 ≥ 90%

---

### Pillar 5. Data & Ingestion — Production-Grade Pipeline

#### 5.1 변경 대상
- `scripts/real_ingest.py` (개편)
- 신규: `app/ingest/`(pipeline orchestration), `app/ingest/parsers/`, `app/ingest/loaders/`, `app/ingest/quality.py`

#### 5.2 설계
1. **DAG화**: Prefect/Apache Airflow lite 또는 `apscheduler` 기반 자체 DAG (scope 부담 적게)
2. **Incremental ingest**: DART rcept_no 기준 워터마크 → 신규/변경분만 처리
3. **병렬 임베딩**: `asyncio.Semaphore(N)` + 배치 호출로 처리량 5~10배 향상
4. **Schema Migration**: Neo4j는 `apoc.schema.assert`, Qdrant는 collection alias로 zero-downtime 교체
5. **Data Quality Gate**:
   - 결측률 / 부채비율 음수 / 매출=0 / 공시 0건 → quarantine 큐
   - 적재 후 셀프 QA(샘플 5건 LLM 검토) → 보고서 자동 생성
6. **Lineage**: 각 Qdrant point에 `ingested_at`, `ingest_version`, `source_url` 메타 강제

#### 5.3 검증 기준
- 5사 × 4년 = 20세트 적재 시간 ≤ 5분(병렬화 후)
- quality gate 위반 0건일 때만 collection alias 스왑

---

### Pillar 6. UX/Frontend 2.0 — Generative · Explorable · HITL

#### 6.1 변경 대상
- `frontend_app/app/page.tsx` (대대적 개편)
- 신규: `frontend_app/app/components/` (Drawer, GraphCanvas, DebateTimeline, EvidenceCard, HITLPanel)

#### 6.2 설계
1. **3-Pane Layout**:
   - Left: Query + Event Stream(에이전트 토론 토큰 단위 스트리밍)
   - Center: Conclusions(재무·리스크·합의문) + Evidence Drawer(클릭 시 원문)
   - Right: Live Knowledge Graph (Cytoscape.js or React Flow) — 노드/엣지가 실시간 추가
2. **토큰 단위 스트리밍**: SSE 이벤트 타입을 `node_start`, `token`, `node_end`, `evidence_added`, `interrupt_requested`, `done`으로 명세 분리
3. **Evidence-First UI**: 결론 카드의 모든 문장에 위첨자 인용 칩 → 클릭 시 원문 chunk + Neo4j path 표시
4. **Debate Timeline**: 시간축에 에이전트 발언 + critic 점수 게이지
5. **HITL Panel**: "여기서 멈춰" 버튼 → state 편집 폼(질의 변경, 가설 주입) → resume
6. **A11y**: 명도 4.5:1, 키보드 포커스, ARIA live region for streaming
7. **i18n**: ko/en 토글
8. **상태 시각**: retrieval mode 배지(real / partial_real / fallback / cached), cost 카운터, 모델 칩

#### 6.3 SSE 이벤트 스키마(계약 고정)
```json
{ "type": "node_start", "node": "finance_analyst", "ts": 1730000000 }
{ "type": "token",      "node": "finance_analyst", "delta": "..." }
{ "type": "evidence_added", "evidence_id": "qd:xxx", "preview": "..." }
{ "type": "node_end",   "node": "finance_analyst", "elapsed_ms": 4321, "cost_usd": 0.012 }
{ "type": "interrupt_requested", "reason": "low_confidence" }
{ "type": "done",       "thread_id": "..." }
{ "type": "error",      "code": "LLM_TIMEOUT", "fallback": true }
```

#### 6.4 검증 기준
- TTFU p95 ≤ 1.5s
- 결론 카드의 모든 문장에 인용 칩 1개 이상
- Lighthouse a11y ≥ 95, 모바일 perf ≥ 80

---

### Pillar 7. Ops · Eval · Security — Production Excellence

#### 7.1 변경 대상
- 신규: `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/cd.yml`, `deploy/helm/`, `app/observability/`, `app/security/`, `eval/`

#### 7.2 Observability
- **Tracing**: OpenTelemetry → OTLP endpoint(자체 Tempo/Jaeger 또는 LangSmith). 노드별 span, LLM 호출 span에 model/usage attribute
- **Metrics**: Prometheus exporter — `analyze_request_total`, `node_latency_seconds`, `llm_cost_usd_total`, `cache_hit_ratio`
- **Logs**: 구조화 JSON(`structlog`), `trace_id` 일관 주입, 민감 필드 마스킹
- **Dashboards**: Grafana 표준 대시보드 1종(latency·cost·error·cache)

#### 7.3 Evaluation
- `eval/golden_set/` — 30문항(시나리오 A/B 포함) 질문/기대근거/기대결론
- `eval/run_eval.py` — RAGAS faithfulness/answer_correctness/context_recall + 자체 휴리스틱(인용 부착률)
- `eval/adversarial/` — prompt injection 30종, jailbreak 10종, 빈 데이터 10종
- CI 게이팅: PR마다 골든셋 30문항 자동 실행, 임계값 미달 시 머지 차단

#### 7.4 Reliability
- **Circuit breaker**: `pybreaker` — Qdrant/Neo4j/LLM별 독립
- **Retry policy**: 단일 정책(`tenacity`) 모듈로 통합
- **Graceful shutdown**: `lifespan`에서 in-flight 요청 대기, drain 시간 초과 시 강제 종료
- **SSE keep-alive**: 15초마다 `: ping`
- **Chaos test**: `eval/chaos.py` — Qdrant down/Neo4j slow/LLM 429 주입 시 fallback 검증

#### 7.5 Security
- **Auth**: OAuth2/JWT (FastAPI dependency). 데모 모드는 `dev-token` 한정 우회
- **Secrets**: `.env` → Doppler/Vault/AWS Secrets Manager 중 1택, 코드에서는 항상 `Settings`만 참조
- **CORS**: 운영 시 화이트리스트(`NEXT_PUBLIC_API_URL` 도메인만)
- **Rate limit**: `slowapi` IP/사용자별
- **PII 마스킹**: 입력/로그/캐시 키 모두에서 주민번호·계좌·카드번호 패턴 즉시 치환
- **Audit log**: append-only 테이블 — (user, query, thread_id, decision, evidence_ids, ts)

#### 7.6 DevOps
- **Containers**: backend / frontend / qdrant / neo4j / postgres(checkpoint) / redis(cache) — `docker-compose.yml`
- **CI**: GitHub Actions — lint(ruff/eslint) → typecheck(mypy/tsc) → unit(pytest/jest) → eval(golden) → build → image push
- **CD**: tag 푸시 시 staging 자동, manual approval 후 production
- **Migrations**: Alembic(Postgres) + `apoc.schema.assert`(Neo4j) + Qdrant alias 스왑

#### 7.7 검증 기준
- Trace에서 단일 요청을 노드·LLM·DB 호출까지 5단계 이상 drill-down 가능
- 의도된 chaos 6종 모두 sane fallback 응답
- Trivy/Snyk 이미지 스캔 high CVE 0건

---

## 4. Phased Roadmap — 6 Sprint, 12 Weeks

> 각 Sprint는 2주, 매 Sprint 종료 시 (a) 데모, (b) RAGAS 게이팅, (c) `CURSOR_LOG.md` 갱신, (d) `7_Progress_Dashboard.md` 갱신을 강제한다.

### Sprint 1 — Foundations (Week 1–2)
- [ ] Pydantic v2 모델 도입(`Evidence`, `FinanceMetrics`, `RiskPoint`, `CriticReport`, `QueryPlan`)
- [ ] `app/state.py` 확장 + `STATE_SCHEMA_VERSION`
- [ ] `LLMRouter` + Provider 추상화 + Mock provider
- [ ] `tenacity` 기반 통일 retry, 통일 timeout
- [ ] 테스트: 기존 4건 + 신규 모델 직렬화 8건
- **Exit**: `pytest -q` 그린, `LLMRouter.invoke(intent=...)` 통일 호출 정착

### Sprint 2 — Retrieval 2.0 (Week 3–4)
- [ ] `query_planner` (LLM decomposition)
- [ ] BM25/sparse 추가(Qdrant sparse) + 가중 hybrid
- [ ] Reranker 통합(BGE 또는 Cohere)
- [ ] LLM Cypher synthesis + 화이트리스트 가드
- [ ] 임베딩 캐시(Redis or sqlite)
- **Exit**: 골든 multi-hop 5건 recall@5 ≥ 0.9

### Sprint 3 — Agent Mesh (Week 5–6)
- [ ] `intent_classifier`, `planner`, `retriever`, `critic`, `reflector` 노드 추가
- [ ] LangGraph subgraph 패턴으로 retriever 캡슐화
- [ ] `tool calling` 표준 인터페이스
- [ ] 모든 결론에 evidence_ids 의무 부착(스키마 검증)
- **Exit**: 시나리오 A에서 critic 재검색 1회+ 발생, 시나리오 B에서 명시적 합의 실패 결론

### Sprint 4 — Memory · UX (Week 7–8)
- [ ] PostgresSaver + 마이그레이션 스크립트
- [ ] `/api/v1/analyze/resume/{thread_id}`, `/interrupt/{thread_id}`
- [ ] SSE 이벤트 스키마 v2(token-level, evidence_added, interrupt)
- [ ] 프론트 3-pane + Cytoscape live graph + Evidence drawer + HITL panel
- [ ] 토큰 단위 스트리밍
- **Exit**: TTFU p95 ≤ 1.5s, 모든 결론에 인용 칩 표시

### Sprint 5 — Eval · Ops (Week 9–10)
- [ ] `eval/golden_set/` 30문항 + RAGAS 통합
- [ ] OpenTelemetry tracing + Prometheus metrics + Grafana 대시보드
- [ ] CI에 골든셋 게이팅
- [ ] Docker compose(전체) + GitHub Actions(lint/test/eval/build/push)
- **Exit**: PR 게이팅 활성, 대시보드 1종 운영, faithfulness ≥ 0.85

### Sprint 6 — Security · Reliability · Polish (Week 11–12)
- [ ] OAuth2/JWT + RBAC(데모/운영자/감사자)
- [ ] PII 마스킹 + 프롬프트 인젝션 가드
- [ ] Circuit breaker + chaos test
- [ ] Audit log + 감사자 뷰
- [ ] 운영 Helm chart + 스테이징 배포
- [ ] 다국어(ko/en), a11y, 모바일 반응형
- **Exit**: 보안 high CVE 0, chaos 6종 통과, Lighthouse a11y ≥ 95

---

## 5. KPI / SLO Dashboard (운영 후 상시 측정)

| 지표 | 대시보드 위치 | 목표 | 경보 임계 |
|---|---|---|---|
| TTFU p95 | Grafana > Latency | ≤ 1.5s | > 3s |
| E2E p95 | Grafana > Latency | ≤ 20s | > 30s |
| RAGAS faithfulness | Grafana > Quality | ≥ 0.85 | < 0.80 |
| Citation 부착률 | Grafana > Quality | 100% | < 99% |
| Cache hit ratio | Grafana > Cost | ≥ 30% | < 15% |
| LLM cost / 1k 요청 | Grafana > Cost | ≤ $X | > 1.5×X |
| Error rate | Grafana > Reliability | ≤ 0.5% | > 2% |
| Fallback 발동율 | Grafana > Reliability | ≤ 5% | > 15% |

---

## 6. 주요 리스크 & 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| LLM provider 가격/정책 변동 | 비용·가용성 | provider 2개 이상 동시 지원 + budget cap |
| 한국어 reranker 성능 한계 | 정확성 | BGE-reranker-v2-m3 + 자체 도메인 fine-tune 옵션 |
| Cypher LLM 생성의 보안 위험 | DML 사고 | read-only 화이트리스트 + 별도 RO 계정 + 단위 테스트 100건 |
| 평가 골든셋 편향 | 측정 왜곡 | 외부 도메인 전문가 1인 검수 라운드 분기 1회 |
| HITL UX 복잡도 | 사용자 혼란 | 기본은 자동, "전문가 모드"에서만 노출 |
| 1인 개발 속도 한계 | 일정 | Sprint 단위 cut-off 룰 + AI 코딩 어시스턴트 적극 활용(`0_System_Context.md` 원칙 유지) |

---

## 7. 합의 사항(존재하는 원칙과의 정합성)

본 기획안은 기존 문서들과 다음과 같이 정합한다.
- `0_System_Context.md`: "방어적 프로그래밍·Fallback·turn_count 차단" 원칙 모두 유지·강화
- `1_Data_Schema_and_State.md`: GraphState 기존 필드 보존 + 추가만 수행(스키마 버저닝으로 호환성 유지)
- `2_GraphRAG_Pipeline.md`: hybrid + community summary로 "Vector + Graph 결합" 사상 확장
- `3_LangGraph_Orchestration.md`: MAX_TURNS·Checkpointer·structured output 강제 그대로, 노드만 확장
- `4_Backend_API_and_SSE.md`: 기존 두 엔드포인트 유지, 신규 `resume/interrupt`만 추가, 이벤트 스키마는 **확장(타입 부여)**으로 하위호환
- `5_Frontend_and_QA.md`: 미니멀 원칙 유지하되, 라이브러리는 React Flow/Cytoscape 1종으로 한정
- `9_Human_Required_Tasks.md`: 본 계획의 "사람 작업" 항목(시크릿/규정/배포 승인)은 9번 문서에 누적
- `11_Product_Blueprint.md`: 본 문서가 11번을 대체하지 않고 **확장**한다(11=원칙, 14=실행)

---

## 8. 즉시 다음 작업 (Sprint 0, 본 문서 합의 직후)

1. 본 문서를 사용자가 검토 → 우선순위 합의 (특히 Pillar 우선순위 / Sprint 5와 6 순서)
2. `requirements.txt`에 후보 의존성 초안 PR (`pydantic`, `tenacity`, `structlog`, `pybreaker`, `opentelemetry-*`, `ragas`, `prometheus-client`, `redis`, `slowapi`)
3. 골든셋 30문항 초안 작성(Sprint 5 선행) — 시나리오 A/B 포함 12문항부터 시작
4. SSE 이벤트 스키마 v2 RFC를 `4_Backend_API_and_SSE.md`에 패치 PR (하위호환 명시)
5. `docker-compose.yml` 골격(backend + qdrant + neo4j + postgres + redis) 초안

---

## 9. 완료 정의 (Done = "현대 최고 수준")

본 마스터플랜은 **다음 모든 조건이 충족될 때만 종료**된다.

- ✅ 5개 NFR 모두 임계값 통과 (정확성·응답성·추적성·회복력·운영성)
- ✅ 7대 Pillar의 Exit 기준 모두 그린
- ✅ 골든셋 30문항 RAGAS 자동 평가가 CI에 게이팅으로 결합
- ✅ 모든 결론이 evidence-grounded (citation 부착률 100%)
- ✅ 단일 명령으로 dev/staging 재현, chaos 6종 통과
- ✅ `9_Human_Required_Tasks.md` 잔여 인간 작업이 5건 이하로 명시되어 있음
- ✅ 모든 변경이 본 문서·`6_..`·`7_..`·`CURSOR_LOG.md`에 추적되어 있음

> 이 문서는 "엔진의 무결성"을 단계적으로 격상시키되, 1인 개발 체제의 생존성을 결코 위배하지 않는다.
> Sprint별 cut-off 룰을 지키는 한, 본 계획은 12주 안에 **현대 엔터프라이즈 GraphRAG의 최상위권** 자리로 본 시스템을 데려갈 수 있다.
