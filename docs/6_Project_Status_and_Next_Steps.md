# 6. Project Status and Next Steps

## 목표

이 프로젝트를 "오프라인 시연이 가능하고, 실연동으로 확장 가능한 GraphRAG 다중 에이전트 데모"로 유지한다.

## 현재 상태

### 강점

- FastAPI + SSE 기반 질의 시작/스트리밍 흐름이 구현되어 있다.
- `langgraph`가 없어도 `LocalFallbackGraph`로 핵심 플로우를 재현할 수 있다.
- 검색 계층이 fallback-first로 설계되어 seed 데이터 기반 시연이 가능하다.
- 기본 회귀 테스트가 있어 노드/라우팅/그래프 조립의 핵심 경로를 검증할 수 있다.
- 프론트엔드가 대시보드와 정적 프로토타입 두 형태로 준비되어 있다.

### 제약

- Neo4j, Qdrant, LLM 실연동은 아직 운영 검증 전 단계다.
- SSE 이벤트 스키마가 동작은 안정적이지만 별도 계약 문서 수준으로 정리되지는 않았다.
- 실데이터 적재 스크립트는 실제 자격 증명과 외부 서비스 상태에 크게 의존한다.
- 배포, 보안 스캔, 비밀 관리, 운영 모니터링은 아직 자동화되지 않았다.

## 다음 작업

> Upgrade Master Plan(`14_Upgrade_Master_Plan.md`) Sprint 0 ~ 6 + post-MVP 핵심 슬라이스가 모두 도입되었다. 잔여는 외부 의존/실연동 검증 단계.

1. **RAGAS 진짜 통합**: `requirements.txt` 에 `ragas`, `datasets` 추가 → `eval/run_eval.py --ragas` 옵션. CI 게이팅 임계 상향 (지금은 휴리스틱 유사 메트릭만 보고).
2. **OpenTelemetry 도입**: `opentelemetry-instrumentation-fastapi` 통합. trace_id ContextVar 와 결합하면 분산 추적 자동.
3. **OAuth2 Authorization Code + PKCE**: Keycloak/Auth0 등 외부 IdP 연동. 현재 JWT 검증기는 그대로 사용 가능.
4. **PostgresSaver 실연동 검증**: `docker compose --profile real up postgres` 로 PostgresSaver 성능/내구성 통합 시험.
5. **HITL Approval Gate**: `interrupt_requested` 발생 시 사용자 승인 후 `resume` 진입 UX 보강.
6. **Hybrid sparse retriever / Reranker / Community Summary**: Retrieval 2.0 후속 — Cohere/BM25 등 외부 의존성 도입 시점에 진행.
7. **다국어 / a11y 보강**: 프론트엔드 i18n + 접근성 자동 검증.

## 완료 기준

- 로컬에서 fallback 경로로 백엔드/프론트/테스트가 재현 가능할 것
- 실연동 필수 조건과 사람 작업이 문서로 분리되어 있을 것
- 핵심 실행 명령과 환경 변수 설명이 루트 문서에 정리되어 있을 것
- 오래된 진행률/환경 기록이 현재 워크스페이스 기준으로 정리되어 있을 것

## 연결 문서

- 현재 실행/구성 안내: `README.md`
- 진행 상태 요약: `7_Progress_Dashboard.md`
- 최근 작업 로그: `CURSOR_LOG.md`
- 사람 전용 작업: `9_Human_Required_Tasks.md`
- 실연동 절차: `10_Real_Integration_Playbook.md`
- 상세 설계 기준: `0_System_Context.md` ~ `5_Frontend_and_QA.md`
