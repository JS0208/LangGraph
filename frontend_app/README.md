# Frontend Dashboard

이 디렉터리는 GraphRAG 다중 에이전트 실행 과정을 시각화하는 Next.js 16 대시보드입니다.
현재 구현은 `app/page.tsx` 단일 페이지를 중심으로 동작하며, 백엔드 SSE 스트림을 직접 구독합니다.

## 요구 사항

- Node.js 20+
- 실행 중인 백엔드 API (`uvicorn app.main:app --reload --port 8000`)

## 실행

```bash
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`으로 접속합니다.

## 환경 변수

기본 백엔드 주소는 `http://localhost:8000`입니다.
다른 주소를 쓰려면 `.env.local`에 아래 값을 넣으세요.

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 현재 동작

- `POST /api/v1/analyze/start` 호출로 `thread_id`를 생성합니다.
- `GET /api/v1/analyze/stream/{thread_id}` SSE를 `EventSource`로 구독합니다.
- `finance_analyst`, `risk_compliance`, `orchestrator`, `system` 이벤트를 카드와 로그 영역에 렌더링합니다.
- 백엔드가 `[DONE]` 이벤트를 보내면 실행 상태를 `complete`로 전환합니다.

## 현재 제약

- SSE 이벤트 스키마는 사실상 `{node_name: payload}` 구조를 전제로 합니다.
- 정교한 그래프 시각화 대신, 현재는 로그/카드 중심 대시보드입니다.
- 정적 프로토타입은 `../frontend_prototype/`에 별도로 유지됩니다.

## 점검

```bash
npm run lint
```
