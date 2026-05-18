# 사전 면접 MVP 전략 — GraphRAG 재무 분석 시스템

> 작성일: 2026-05-18 | 목적: 내일 도슨티 사전 면접 시연 준비

---

## 1. 시스템 한 줄 요약 (면접관에게 설명할 버전)

> "DART 공시 데이터를 기반으로, LangGraph로 연결된 **8개 전문 에이전트**가 기업의 재무 지표와 리스크를 자동 분석하고, Neo4j 지식 그래프와 Qdrant 벡터 DB를 결합한 **하이브리드 RAG**로 검색 정확도를 높인 FastAPI + Next.js 서비스입니다."

---

## 2. 8개 노드 전체 흐름 (암기 필수)

```
사용자 질의
    ↓
① intent_classifier     → 질의 의도 분류 (in_scope / out_of_scope)
    ↓
② retrieve_context      → 하이브리드 RAG (Qdrant 벡터 + Neo4j 2-hop 그래프)
    ↓
③ finance_analyst       → 재무 지표 LLM 추출 (debt_ratio, insight)
    ↓
④ risk_compliance       → 공시 기반 리스크 포인트 추출
    ↓
⑤ critic                → 인용 누락·일반론·모순 점수화 (disagreement_score)
    ↓ (score ≥ 0.5이면)
⑥ reflector             → 쿼리 가중치 재정제 → ② 재실행 (최대 2회)
    ↓
⑦ orchestrator          → 합의 결정 + SSE 토큰 스트리밍
    ↓
⑧ generate_final_report → 최종 보고서 JSON 반환
```

**자가 교정 루프**: critic이 품질이 낮다고 판단하면 reflector가 쿼리 가중치를 1.2배 부스트해 retrieve_context를 재실행 (MAX_REFLEXIONS=2로 무한루프 차단)

---

## 3. MVP 데모 모드 — 외부 의존성 없이 실행

### 핵심 원칙: `RETRIEVAL_FORCE_FALLBACK=1`

실제 Qdrant·Neo4j 서버 없이도 **seed 데이터**로 전체 파이프라인이 동작한다.
LLM API 키가 없으면 rule-based fallback 분석기가 자동 작동한다.

### .env MVP 설정 (→ 바로 적용 필요)

```env
# ↓ 이 한 줄이 MVP 모드의 핵심
RETRIEVAL_FORCE_FALLBACK=1

# 실 LLM 키가 있으면 유지, 없으면 빈 값으로 두면 fallback 분석 동작
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=

# 외부 DB 연결 불필요 (값이 있어도 FORCE_FALLBACK=1이면 미호출)
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=
QDRANT_URL=
QDRANT_API_KEY=

NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 실행 순서

```bash
# 1. 백엔드 (터미널 1)
cd [프로젝트 루트]
pip install fastapi uvicorn pydantic python-dotenv httpx structlog tenacity
uvicorn app.main:app --reload --port 8000

# 2. 프론트엔드 (터미널 2)
cd frontend_app
npm install
npm run dev   # → http://localhost:3000
```

---

## 4. 데모 시나리오 (면접 당일 시연 흐름)

### 추천 쿼리 (seed 데이터 있음)
> **"카카오의 2024년 3분기 실적과, 자회사 카카오게임즈의 규제 리스크가 본사에 미치는 영향을 분석해."**

### 시연 포인트 (설명 멘트와 함께)

| 단계 | 화면에 보이는 것 | 설명 멘트 |
|------|-----------------|----------|
| ① intent_classifier 실행 | "Intent: finance_risk" 표시 | "질의가 재무+리스크 복합임을 자동 분류합니다" |
| ② retrieve_context 실행 | Evidence count, mode 표시 | "Neo4j 2-hop + Qdrant 하이브리드로 관련 증거를 수집합니다" |
| ③④ 분석 에이전트 | debt_ratio, risk_points | "각 역할이 분리된 에이전트가 병렬처리합니다" |
| ⑤ critic 실행 | disagreement_score 표시 | "품질 게이트로 환각을 제어합니다" |
| ⑦ orchestrator | 토큰이 실시간으로 흘러나옴 | "SSE 스트리밍으로 사용자가 즉시 결과를 봅니다" |
| ⑧ 최종 리포트 | 우측 패널에 종합 분석 | "합의된 분석 결과가 structured output으로 전달됩니다" |

---

## 5. 개발 중인 기능 — 면접관 질문 시 대응 방안

면접관이 "이건 왜 안 되나요?"라고 물을 수 있는 부분들:

| 기능 | 현재 상태 | 설명 방법 |
|------|----------|----------|
| 실 Qdrant 벡터 검색 | Fallback 모드 | "프로덕션 환경에서는 Gemini 임베딩 → Qdrant에 저장한 실 데이터로 동작합니다. 오늘은 네트워크 안정성을 위해 seed 데이터로 시연합니다." |
| Neo4j 그래프 DB | Fallback 모드 | "관계 데이터는 Neo4j에 2-hop 탐색 구조로 저장되어 있고, 실제 연동 코드는 `real_clients.py`에 구현돼 있습니다." |
| DART 실시간 수집 | 인제스트 파이프라인 별도 | "OpenDartReader로 수집 → 전처리 → 임베딩 저장까지 `app/ingest/` 파이프라인이 있습니다." |
| LangGraph checkpointer | MemorySaver/LocalFallback | "PostgresSaver 도입 전 단계이며, 체크포인팅 구조는 이미 `memory/saver_factory.py`에 추상화돼 있습니다." |

---

## 6. 예상 기술 질문 & 답변

### Q: "7개 노드라고 하셨는데, 정확히 어떤 노드들인가요?"
→ 위 2번 참고. **8개가 맞습니다** (이전 인터뷰에서 reflector를 빠뜨렸을 가능성). 자가교정 루프가 핵심 차별점임을 강조.

### Q: "critic 노드는 어떤 기준으로 재검색을 요청하나요?"
→ `disagreement_score ≥ 0.5` AND `reflexion_count < 2` AND `evidence가 없을 때` 세 조건이 동시에 충족돼야 reflector를 호출합니다.

### Q: "하이브리드 RAG에서 벡터 검색과 그래프 검색을 어떻게 합치나요?"
→ Qdrant 결과(의미 기반)와 Neo4j 2-hop 결과(관계 기반)를 각각 Evidence 객체로 변환한 뒤, reranker가 relevance score로 통합 정렬합니다.

### Q: "환각을 어떻게 제어하나요?"
→ 세 가지 레이어: ① critic의 disagreement_score로 품질 측정 → ② reflector의 재검색 루프로 자가교정 → ③ MAX_REFLEXIONS=2로 무한루프 방지.

### Q: "DART API 데이터는 어떻게 수집·저장했나요?"
→ **DART API 복습 자료** 별도 문서 참고 (`면접준비_DART_API_복습.md`)

---

## 7. 당일 체크리스트

- [ ] `.env`에 `RETRIEVAL_FORCE_FALLBACK=1` 설정 확인
- [ ] `uvicorn app.main:app --reload` 백엔드 정상 기동 확인
- [ ] `npm run dev` 프론트엔드 정상 기동 확인
- [ ] 카카오 쿼리로 전체 파이프라인 end-to-end 1회 테스트
- [ ] 삼성전자 쿼리도 테스트 (seed 데이터 추가됨)
- [ ] 브라우저에서 Knowledge Graph 시각화 정상 렌더링 확인
- [ ] Evidence Drawer 동작 확인
