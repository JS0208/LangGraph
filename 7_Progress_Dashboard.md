# 7. Progress Dashboard

## 현재 상태

- 백엔드 fallback 실행 경로: 안정적
- FastAPI + SSE 인터페이스: v1 100% 호환 + **v2 type 기반 동시 송출**, 15s ping, evidence_added, interrupt_requested, done/error
- Next.js 대시보드: v2 이벤트 수용, **Evidence Drawer**, **Knowledge Graph live SVG**, **Interrupt 버튼** 도입
- 자동 테스트: **126/126 그린**
- Pydantic v2 모델 / LLMRouter / 통일 retry: 도입 완료 (Sprint 1)
- 임베딩/플랜 캐시 (in-memory + sqlite) / Query Planner / Cypher Safety: 도입 완료 (Sprint 2)
- intent_classifier / critic / reflector / disagreement_score 라우팅: 도입 완료 (Sprint 3)
- StateStore / EpisodeStore + interrupt/resume API: 도입 완료 (Sprint 4)
- in-memory metrics (Prometheus text) + structlog (옵션) + request_id 미들웨어: 도입 완료 (Sprint 5-A)
- 골든셋 v0 (**30문항**): 도입 완료, fallback 평가 **pass_rate 100% / intent 100% / cite 100% / entity 100%**
- RAGAS-like 자체 메트릭 (context_recall / faithfulness / answer_relevance): 도입 완료 (실 LLM 환경에서 의미)
- Guardrails (PII/prompt-injection/out_of_scope) + Audit log + Auth (`disabled|token|jwt`): 도입 완료
- 자체 JWT (HS256, 의존성 0): 도입 완료
- 자체 Circuit Breaker + qdrant/neo4j/LLM 적용 + chaos 테스트: 도입 완료
- CORS 화이트리스트 + request_id + 메트릭 미들웨어: 도입 완료
- LLM 토큰 stream 인터페이스 + SSE `token` 이벤트 progressive 송출 + 프론트 점진 표시: 도입 완료
- LangGraph PostgresSaver/SqliteSaver wire-compatible factory (`CHECKPOINTER_DSN`): 도입 완료
- GitHub Actions CI (pytest + audit + golden eval 게이팅): 도입 완료
- Docker Compose 골격: 도입 완료
- 실연동 운영화: ENV 키 주입 시 자동 활성

## Upgrade Master Plan 진행률 (`14_Upgrade_Master_Plan.md` 기준)

| Sprint | 상태 | 비고 |
|---|---|---|
| Sprint 0 — Setup | 완료 | requirements / docker-compose / 골든셋 / SSE v2 RFC |
| Sprint 1 — Foundations | 완료 | schemas / state 확장 / retry / LLMRouter / llm_structured 리팩터 |
| Sprint 2 — Retrieval 2.0 | 완료(부분) | cache, query_planner(휴리스틱+LLM), cypher_safety, query_router에 evidence/plan 주입. Hybrid sparse/Reranker/Community Summary는 외부 의존성 도입 시 후속 |
| Sprint 3 — Agent Mesh | 완료 | intent_classifier / critic / reflector 노드 + disagreement_score 라우팅 + LocalFallbackGraph 확장 |
| Sprint 4 — Memory · UX | 완료 | StateStore/EpisodeStore + interrupt/resume/state API + SSE v2 동시 송출 + 프론트 Evidence Drawer/KG/HITL |
| Sprint 5 — Eval · Ops | 완료(부분) | 골든셋 30문항 + run_eval JSON + GitHub Actions CI(audit + eval 게이팅) + in-memory metrics(Prometheus text) + structlog. RAGAS / OTel는 후속 |
| Sprint 6 — Security · Reliability | 완료(부분) | guardrails(PII/prompt-injection) + audit log + dev token + CORS 화이트리스트 + 자체 circuit breaker. OAuth2/JWT 본격 도입 및 chaos 정밀화는 후속 |

## 세부 구분

1. Core Demo Runtime: Stable
2. Retrieval and Fallback Safety: Stable + 가드레일 1차 차단 도입
3. Frontend Visualization: 강화 (v2 이벤트, Evidence Drawer, KG SVG, Interrupt 버튼)
4. Automated Verification: 105 tests (Sprint 4-6에서 35건 추가)
5. Real Integration Readiness: Partial
6. Production Operations: Sprint 5-A/6 부분 도입 (metrics/audit/auth)
7. Schema/Contract Versioning: Sprint 1 도입 (`STATE_SCHEMA_VERSION`), Sprint 4-C에서 SSE v2 송출 시작

## 측정 지표 (fallback baseline)

| 지표 | Sprint 3 | Sprint 5 | **현재 (Sprint 6+)** | 목표 |
|---|---|---|---|---|
| pytest 그린 | 70/70 | 105/105 | **126/126** | 유지 |
| 골든셋 문항 수 | 12 | 30 | 30 | 30+ |
| pass_rate | 83.33% | 96.67% | **100%** | 90%+ |
| intent_accuracy | 100% | 100% | 100% | 95%+ |
| entity_recall | 80% | 95.83% | **100%** | 95%+ |
| citation_attachment_rate | 100% | 100% | 100% | 100% |
| ragas-like context_recall | — | — | 4.17% (fallback) | 실 LLM 환경에서 재측정 |
| ragas-like faithfulness | — | — | 0.00% (fallback) | 실 LLM 환경에서 재측정 |
| ragas-like answer_relevance | — | — | 13.27% (fallback) | 실 LLM 환경에서 재측정 |

## 기준 문서

- 현재 기능/제약: `README.md`
- 상세 상태와 남은 과제: `6_Project_Status_and_Next_Steps.md`
- 사람 전용 작업: `9_Human_Required_Tasks.md`
- 업그레이드 마스터플랜: `14_Upgrade_Master_Plan.md`
- 진행 로그: `CURSOR_LOG.md`
