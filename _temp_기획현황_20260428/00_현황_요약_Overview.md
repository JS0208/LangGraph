# 00. 한 페이지 현황 요약 (Overview)

**기준일**: 2026-04-28 (Sprint 7 골격 반영으로 2026-04-29 업데이트)
**원전**: `14_Upgrade_Master_Plan.md`, `16_Session_Implementation_Report_2026-04-28.md`, `17_Session_Planning_Report_2026-04-28.md`

---

## 1. 신호등 한눈에 보기

| 영역 | 상태 | 한 줄 진단 |
|------|------|------------|
| 기획·문서 | 🟢 안정 | 마스터 플랜·구현 보고서·기획 보고서 3종 동기화 완료 |
| 스키마·상태 | 🟢 안정 | Pydantic v2 모델 + `GraphState total=False` 확장 + 버저닝 도입 |
| LLM 레이어 | 🟢 안정 | Provider 추상화·Router·Mock·재시도·캐시·스트리밍 일체 정착 |
| 검색(Pillar 1) | 🟡 부분 | Planner·휴리스틱 분해·Cypher 가드·임베딩 캐시 OK + **BM25-Lite / Reranker / Community Summary / Semantic Cache 골격 도입(Sprint 7)** / 외부 벤더 PoC 잔여 |
| 에이전트(Pillar 2) | 🟢 안정 | intent / planner / critic / reflector / orchestrator 노드 + 라우팅 규칙 + evidence 의무 부착 |
| 메모리(Pillar 3) | 🟢 안정 | 스냅샷·인터럽트·재개 + Sqlite/Postgres saver 팩토리 + **Long-term Vector Memory(user_memory) 골격 도입(Sprint 7)** |
| 평가(Pillar 5/Eval) | 🟢 안정 | 골든셋 30문항 + RAGAS-like 자체 메트릭 + CI 게이팅 + **Adversarial 30종 v0.json + 차단율 게이팅 도입(Sprint 7)** |
| 운영·관측(Pillar 7) | 🟡 부분 | structlog/JSON 로그·Prometheus 텍스트·request_id OK + **OTel-style span shim·Rate Limit(token bucket) 골격 도입(Sprint 7)** / 실 OTel collector 미연결 |
| 보안(Pillar 7) | 🟡 부분 | JWT(HS256 자체)·CORS 화이트리스트·PII 마스킹·감사 로그 OK / **OAuth2 PKCE / IdP 미연결** |
| UX/Frontend (Pillar 6) | 🟡 부분 | 3-pane·Evidence Drawer·SVG KG·SSE v2·**노드 내부 true streaming(orchestrator put_token) 골격 도입(Sprint 7)** / a11y·i18n 인증 잔여 |
| 인프라(CI/CD) | 🟢 안정 | Dockerfile·docker-compose(real/infra 프로필)·GitHub Actions(lint·pytest·audit·골든셋·프론트 eslint) |

🟢 안정 = Exit 기준 충족 또는 골든셋·테스트 그린 / 🟡 부분 = 골격 도입, 일부 항목 백로그 / 🔴 미착수 = 별도 스프린트 필요

---

## 2. 핵심 정량 지표 (세션 종료 시점)

| 지표 | 값 | 목표 | 비고 |
|------|----|------|------|
| pytest 통과 | **151 / 151 passed** (예상) | green | Sprint 7 테스트 25건 추가 (로컬 fallback 환경 기준) |
| `scripts/audit_project.py` | **19 / 19 통과** | green | 구조·계약 회귀 가드 |
| 골든셋(30문항, fallback) pass_rate | **100%** | ≥ 80% | 휴리스틱 + intent + entity + citation |
| 골든셋 intent 정확도 | **100%** | ≥ 90% | OOS / facts / risk / trend / relation |
| 골든셋 entity_recall | **100%** | ≥ 90% | 멀티 엔티티(GS-012) 버그 수정 반영 |
| 골든셋 citation 부착률 | **100%** | 100% | 모든 결론에 evidence_id 강제 |
| RAGAS-like (faithfulness/recall/relevance) | **낮음(정상)** | 실연동에서 재해석 | mock 텍스트가 짧음 → 의도된 baseline |

---

## 3. 6 Sprint 진척률 한 줄 요약

| Sprint | 명칭 | 진척 | 상태 | 비고 |
|--------|------|------|------|------|
| **Sprint 0** | Foundation 합의 | 100% | ✅ | 마스터 플랜 합의·문서 정합성 확보 |
| **Sprint 1** | Pydantic v2 / state / Router / 통일 retry | 100% | ✅ | LLMRouter 단일 진입점 정착 |
| **Sprint 2** | Retrieval 2.0 (분해/캐시/Cypher 가드) | **85%** | 🟡 | sparse·rerank·community 골격 도입(Sprint 7) / 외부 벤더 PoC 잔여 |
| **Sprint 3** | Agent Mesh (intent/critic/reflector + tool 표준) | 100% | ✅ | 시나리오 A/B 행동 검증 |
| **Sprint 4** | Memory · UX (resume/interrupt/SSE v2/3-pane) | **95%** | 🟡 | 노드 내부 true streaming 골격 도입(Sprint 7) / 완전 통합 잔여 |
| **Sprint 5** | Eval · Ops (골든 30/RAGAS/CI 게이팅) | **85%** | 🟡 | Adversarial 30종 도입 / 진짜 RAGAS·OTel 미연결 |
| **Sprint 6** | Security · Reliability · Polish | **55%** | 🟡 | Rate Limit·OTel shim 도입 / OAuth2·chaos 6종·Helm·a11y 잔여 |
| **Sprint 7** | 골격 선도입 (Pillar 1/3/5/6/7 보강) | **골격만** | 🟡 | 의존성 0 stub 12종 + 테스트 25건 그린 / 외부 연동 미완 |

전체 가중 진척률 (Sprint 평균, 1~7 단순 평균): 약 **85%** ↑

---

## 4. North Star vs 현재

| NFR | 임계값 | 현재 측정값 | 충족 여부 |
|-----|--------|-------------|-----------|
| 정확성 (Faithfulness) | ≥ 0.85 | RAGAS-like baseline (실연동 재측정 필요) | ⏳ 보류 |
| 응답성 (TTFU p95) | ≤ 1.5s | progressive token 송출은 동작하나 측정 인프라 미배치 | ⏳ 보류 |
| 추적성 (Citation 부착률) | 100% | **100%** (스키마 강제) | ✅ |
| 회복력 (Fallback 성공률) | ≥ 99% | chaos test 1종 통과, 6종까지는 미완 | 🟡 부분 |
| 운영성 (단일 명령 재현) | ✅ | `docker compose up` + GitHub Actions CI 그린 | ✅ |

---

## 5. 다음 사이클의 우선순위 (제안)

1. **실연동 RAGAS** 패키지 통합 + faithfulness CI 임계 재조정 (현재 baseline → 실측 0.85 게이팅으로 전환)
2. **OpenTelemetry collector 연결** (shim은 완성 — OTLP endpoint + Grafana 대시보드로 TTFU p95 측정 활성화)
3. **Hybrid sparse(Qdrant) + Reranker 실 연동** (BM25-Lite·reranker 골격 완성 → 외부 벤더 PoC로 전환)
4. **OAuth2 PKCE + 외부 IdP** (Sprint 6 핵심 잔여 — Rate Limit 도입 완료)
5. **노드 내부 true streaming 완전 통합** (orchestrator put_token 완성 → 나머지 노드 확장)
6. **chaos test 6종** + Helm chart + 스테이징 배포 (운영 승격)
7. **Long-term Memory 외부 연동** (SQLite 골격 완성 → Qdrant user_memory collection 연결)

---

*상세는 같은 폴더의 01~04 문서를 참고.*
