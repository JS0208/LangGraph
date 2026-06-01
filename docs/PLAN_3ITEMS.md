# GraphRAG — 3개 추가 개선 항목 기획안

> 작성 기준: Sprint 7/8 구현 완료 이후 다음 우선 과제
> 각 항목은 **기획 → 설계 결정 → 구현 범위 → 검증 기준** 순으로 기술한다.

---

## 항목 A. RAGAS 지표(faithfulness, answer_correctness) CI 게이팅 통합

### 현황 분석

`eval/run_eval.py`에 자체 구현한 휴리스틱 RAGAS-like 지표가 존재한다
(`ragas_like_faithfulness`, `ragas_like_answer_relevance`).
문제는 세 가지다:

1. **answer_correctness 지표 없음** — 골든셋에 `ground_truth` 필드가 없어 정답 대비 정확도를 측정할 수 없다.
2. **CI 게이팅 조건이 pass_rate(75%) 하나뿐** — faithfulness 0.85, answer_correctness 0.80 목표치(v0.json scoring_targets)가 CI에서 실제로 강제되지 않는다.
3. **실제 RAGAS 라이브러리 미통합** — 키워드 포함 여부 휴리스틱은 LLM 기반 평가 대비 신뢰도가 낮다.

### 설계 결정

| 결정 | 근거 |
|------|------|
| CI는 항상 fallback 모드(LLM 없음)로 실행 → 휴리스틱 지표 사용 | 외부 API 키 없이 결정론적 CI 보장 |
| 실제 RAGAS는 `--ragas` 플래그 시 활성화 (LLM 필요) | 수동 품질 감사 / PR 리뷰 단계에서 사용 |
| CI 게이팅 임계값: faithfulness >= 0.55, answer_relevance >= 0.50 (heuristic) | 휴리스틱이 실제 RAGAS보다 보수적이므로 낮게 설정 |
| 실 RAGAS 임계값: faithfulness >= 0.75, answer_correctness >= 0.65 | `scoring_targets`보다 5~15%p 낮게 — 점진 상향 전략 |
| 골든셋 v0.json에 `ground_truth` 필드 추가 | answer_correctness 계산의 기준 정답 |

### 구현 범위

```
eval/
  ragas_gate.py          ← 신규: 실 RAGAS + 휴리스틱 fallback 통합 모듈
  run_eval.py            ← 수정: answer_correctness 추가, --ragas 플래그 연결
  golden_set/v0.json     ← 수정: 전 시나리오에 ground_truth 필드 추가
.github/workflows/ci.yml ← 수정: faithfulness + answer_relevance 게이트 조건 추가
```

### 검증 기준

- CI 빌드가 `ragas_like_faithfulness < 0.55` 또는 `ragas_like_answer_relevance < 0.50`일 때 실패(exit 1)
- `python eval/run_eval.py --json` 출력에 `answer_correctness` 필드 존재
- `python eval/run_eval.py --ragas` 플래그가 ragas 미설치 시 graceful fallback

---

## 항목 B. LLM 토큰 스트리밍 + SSE v2 결합으로 실시간 응답성 개선

### 현황 분석

`OpenAICompatProvider.astream()`은 OpenAI SSE 토큰을 실시간으로 yield하는 코드가 이미 있다.
`streaming.py`의 `put_token()` / `drain_until_node_end()`도 구현되어 있다.
그러나 **실제 LLM 노드들은 여전히 `router.invoke()`(블로킹)를 사용**한다.

```
현재 흐름:
finance_analyst → invoke() → 전체 응답 수신 후 한 번에 state 업데이트
                ↓
SSE 클라이언트는 노드가 끝날 때까지 침묵

목표 흐름:
finance_analyst → stream() → 토큰마다 put_token() → drain_until_node_end()
                ↓
SSE 클라이언트가 토큰 단위로 실시간 수신
```

### 설계 결정

| 결정 | 근거 |
|------|------|
| JSON 모드 응답(finance_metrics, risk_points)도 스트리밍 | JSON은 끝에서 파싱하면 되므로 스트림 중간에 파싱 불필요 |
| 토큰 누적 후 파싱 → 기존 fallback 로직 재사용 | API 변경 최소화 |
| `put_token()` 호출은 thread_id가 있을 때만 | 단위 테스트 환경(thread_id 없음)에서 no-op |
| `evaluator` / `planner` intent를 KNOWN_INTENTS에 추가 | router.stream() 경로 정상 동작 |
| 스트리밍 실패 시 invoke() fallback 유지 | 안정성 우선 |

### 구현 범위

```
app/agents/llm_structured.py   ← 수정: invoke() → stream() + put_token() 연결
app/llm/router.py              ← 수정: KNOWN_INTENTS에 'evaluator' 추가, stream() 개선
```

SSE 엔드포인트(`endpoints.py`)와 `streaming.py`는 이미 완성 — 변경 없음.

### 검증 기준

- `extract_finance_metrics()` 호출 중 `thread_id`가 설정되어 있으면 SSE 클라이언트가 토큰 수신
- 스트리밍 실패 시 기존 invoke() 결과와 동일한 JSON 응답 반환
- `test_llm_stream.py` 기존 테스트 통과

---

## 항목 C. Multi-entity 쿼리(복수 기업 비교) 분해 정확도 보완

### 현황 분석

현재 `_heuristic_plan()`의 멀티 엔티티 처리 문제점:

1. **연도 추출이 단일** — "삼성전자 2023년과 SK하이닉스 2024년 비교" 시 두 연도를 별도 추출 불가
2. **비교 intent 미탐지** — 비교 쿼리도 `facts`로 분류되어 검색 전략이 단일 팩트 조회와 동일
3. **회사별 병렬 검색 없음** — `hybrid_retrieve()`가 단일 company/year를 받으므로 복수 회사 쿼리에서 첫 번째 회사만 검색
4. **COMPANY_ALIAS_MAP 커버리지 부족** — LG전자, 현대자동차, 셀트리온 등 주요 상장사 미등록

### 설계 결정

| 결정 | 근거 |
|------|------|
| 비교 키워드(비교, 대비, vs, versus 등) 탐지 시 intent="trend" | trend가 비교 분석에 가장 가까운 기존 intent |
| 회사별 연도 개별 추출 (`extract_company_year` per mention) | "삼성 2023, SK 2024" 같은 혼합 연도 쿼리 대응 |
| 병렬 검색: `asyncio.gather()` 로 회사별 `qdrant_search()` 동시 실행 | 직렬 대비 응답시간 N배 개선 |
| 결과 병합: source_type + company_name 기반 dedup | 중복 청크 제거 |
| COMPANY_ALIAS_MAP 확장: 20→50+ 항목 | 주요 코스피/코스닥 상장사 커버 |
| SubQuery에 `comparison_pair` 메타 추가 없이 기존 스키마 유지 | 스키마 변경 없이 기존 노드 호환성 유지 |

### 구현 범위

```
app/retrieval/real_clients.py    ← 수정: COMPANY_ALIAS_MAP 확장, extract_companies() 개선
app/retrieval/query_planner.py   ← 수정: _heuristic_plan() 비교 intent 탐지, 연도 per-company 추출
app/retrieval/query_router.py    ← 수정: hybrid_retrieve_multi() 추가 (병렬 검색)
app/retrieval/multi_entity.py    ← 신규: 복수 회사 병렬 검색 코디네이터
```

### 검증 기준

- "삼성전자와 SK하이닉스의 부채비율 비교" → `sub_queries` 2개, 각 `target_company` 일치
- "삼성전자 2023년과 SK하이닉스 2024년 비교" → 각 sub_query의 `target_year` 별도 추출
- 골든셋 GS-010 (비교 시나리오) entity_match 통과
- 병렬 검색 응답시간이 직렬 대비 ≥ 30% 단축 (단위 테스트 mock 측정)

---

## 우선순위 및 구현 순서

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | **C. Multi-entity** | 기반 데이터 품질 개선 → 다른 지표에 영향 |
| 2 | **B. 토큰 스트리밍** | 사용자 체감 응답성 직접 개선 |
| 3 | **A. RAGAS CI 게이팅** | 품질 기준 강화 — 위 두 항목 구현 후 측정 의미 있음 |

---

*작성일: 2026-05-24 | 대상 브랜치: main*
