# Real Integration Playbook (Human-Executed)

아래는 질문하신 "실 연동은 내가 직접해야 하는가?"에 대한 구체 절차입니다.

## 결론
네, **실 연동(실 API 키/실 DB/운영 승인)은 사람(사용자)이 직접** 수행해야 합니다.
이 저장소는 그 전에 필요한 구조/검증/프로토타입을 준비한 상태입니다.

## Step-by-step
1. **Python 환경 준비**
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`

2. **실 서비스 준비**
   - Neo4j 인스턴스 생성 (Aura 또는 사내)
   - Qdrant 인스턴스 생성 (Cloud 또는 사내)
   - LLM Provider API 키 발급 (Gemini/Claude 등)

3. **시크릿 주입**
   - 예시 환경변수(실제 값으로 교체):
     - `NEO4J_URI=...`
     - `NEO4J_USER=...`
     - `NEO4J_PASSWORD=...`
     - `QDRANT_URL=...`
     - `QDRANT_API_KEY=...`
     - `LLM_API_KEY=...`

4. **실 연동 코드 확장 포인트**
   - `app/retrieval/query_router.py`: seed fallback 대신 실제 Qdrant/Neo4j 조회 로직 추가
   - `app/agents/nodes.py`: mock 분석 로직 대신 실제 LLM structured output 연결
   - `app/api/endpoints.py`: 이벤트 스키마/timeout/retry 정책 운영 수준으로 고도화

5. **실행 검증**
   - `pytest -q`
   - `python scripts/audit_project.py`
   - `uvicorn app.main:app --reload --port 8000`
   - `frontend_prototype/index.html`에서 실제 요청/스트리밍 확인

6. **운영 전 체크리스트 (필수)**
   - 보안 점검(키 노출/로그 마스킹)
   - 컴플라이언스 점검(금융 규정/로그 보관)
   - 성능 점검(TTFU, P95 latency)
   - 장애 대응(Fallback/재시도/알람)
