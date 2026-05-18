# 5. Frontend and QA

[CURSOR AI 작업 지침]
이 문서는 백엔드(FastAPI)에서 스트리밍되는 LangGraph 에이전트들의 토론 과정을 시각화하기 위한 Next.js 프론트엔드 명세다.
본 프로젝트는 '엔진의 논리적 무결성' 증명이 핵심이므로, 화려한 애니메이션이나 복잡한 전역 상태 관리(Redux 등)를 절대 도입하지 마라. Vercel AI SDK와 Tailwind CSS(필요시 shadcn/ui)만을 사용하여 가장 미니멀하고 직관적인 대시보드를 구성하라.

[현재 구현 메모]
- 현재 프론트엔드 구현은 `frontend_app/app/page.tsx` 중심의 단일 페이지다.
- SSE 구독은 Vercel AI SDK가 아니라 브라우저 `EventSource`를 직접 사용한다.
- 정적 시연용 프로토타입은 `frontend_prototype/index.html`에 별도로 유지된다.

5.1. 핵심 기술 스택 및 구조 (app/ App Router 기반)

프레임워크: Next.js 16 (App Router)

상태 관리 및 스트리밍: 브라우저 `EventSource` 기반 SSE 구독

스타일링: Tailwind CSS

[UI 레이아웃 강제 (2-Pane Dashboard)]

복잡한 라우팅 없이 단일 페이지(page.tsx) 내에서 두 개의 패널로 분리하여 렌더링하라.

Left Pane (대화 및 제어 패널): 사용자 질의 입력창, 에이전트들의 실시간 사고 과정(Log) 스트리밍 텍스트.

Right Pane (Generative UI 패널): 오케스트레이터가 도출한 최종 재무 지표 및 리스크 합의문, 그리고 출처가 되는 지식 그래프(Knowledge Graph)의 핵심 노드 시각화.

5.2. Generative UI 스트리밍 연동 로직 (`frontend_app/app/page.tsx`)

백엔드의 GET /api/v1/analyze/stream/{thread_id} 엔드포인트에서 넘어오는 SSE 데이터를 파싱하여 화면에 뿌려준다.

상태 기반 컴포넌트 렌더링:
스트리밍되는 데이터의 node 값에 따라 다른 UI 컴포넌트를 렌더링하라.

node === "finance_analyst": 파란색 테마의 카드 컴포넌트에 정량적 지표 표시.

node === "risk_compliance": 붉은색 테마의 카드 컴포넌트에 경고 아이콘과 함께 리스크 표기.

node === "orchestrator": 최종 결론을 굵은 텍스트와 요약 리스트로 표기.

[🚨 생존 지침] 복잡한 그래프 시각화 우회:
Neo4j의 노드와 엣지를 D3.js나 React Flow로 화려하게 그리려다 시간을 낭비하지 마라. 초기에는 Mermaid.js 문자열을 생성하여 렌더링하거나, 단순히 연관된 기업명과 관계를 태그(Tag) 형태로 나열하는 것으로 충분하다.

6. QA 테스트 셋 및 시연 시나리오 (최종 검증)

마일스톤 5월 QA 단계 및 교수진 최종 평가 시연을 위해, 아래의 '엣지 케이스 시나리오'를 통과하는지 검증하는 테스트 코드를 작성하라.

6.1. 핵심 시연 시나리오 (Mock Data 주입)

API나 데이터 파싱 오류를 대비하여, 무조건 성공적으로 작동해야 하는 '골든 경로(Golden Path)' 시나리오를 하드코딩해 두어라.

시나리오 A (자회사 리스크 전이):

질의: "카카오의 2024년 3분기 실적과, 자회사 카카오게임즈의 규제 리스크가 본사에 미치는 영향을 분석해."

기대 결과(검증 기준): 1. 재무 에이전트가 본사의 부채비율 상승을 지적.
2. 리스크 에이전트가 자회사 규제 공시를 지적.
3. 오케스트레이터가 '자회사 리스크로 인한 본사 지분 가치 하락 우려'라는 연결된(Graph) 인사이트 도출.

시나리오 B (에이전트 데드락 방지 검증):

의도적으로 상충되는 데이터를 주입하여 에이전트 간 의견 충돌 유발.

기대 결과: 정확히 turn_count === 3 (또는 설정값)에서 토론이 강제 종료되고, 오케스트레이터가 "합의에 도달하지 못해 추가 데이터 확인 요망"이라는 Fallback 결론을 내는지 확인.

6.2. 로컬 Fallback 실행 스크립트 (scripts/run_local_demo.py)

평가 당일 인터넷이 끊기거나 외부 API(DART, OpenAI/Anthropic 등) 과금 한도가 초과될 최악의 상황을 대비한다.
사전에 캐싱된(Cached) LLM 응답과 Local JSON 파일만을 사용하여 프론트엔드에 스트리밍을 흉내 내는 완전한 오프라인 시연 스크립트를 준비하라.