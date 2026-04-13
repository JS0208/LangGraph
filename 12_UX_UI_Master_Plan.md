# 12. UX UI Master Plan

## 목적

이 문서는 사용자 경험 원칙, 정보 구조, 상호작용 흐름을 정리한 UI/UX 기준 문서다.

## UX 비전
- 목표: 금융 의사결정 지원에서 **신뢰성(Trust), 속도(Speed), 해석가능성(Interpretability)**를 동시에 달성.
- 핵심 UX 원칙:
  1. **Zero Ambiguity**: 사용자는 항상 "지금 시스템이 무엇을 하는지"를 알아야 한다.
  2. **Evidence First**: 결론보다 근거(지표/리스크/출처)를 먼저 보여준다.
  3. **Progressive Disclosure**: 초보자는 요약, 전문가는 상세 로그/근거를 즉시 확장 가능.
  4. **Failure-Transparent**: 실패를 숨기지 않고 fallback 여부를 명시한다.

## 정보 구조
- 좌측 패널: 입력/진행상태/에이전트 라이브 로그
- 우측 패널: 최종 합의, 재무 지표 카드, 리스크 카드, 상태 배지
- 하단: 이벤트 타임라인(스트리밍 이벤트 이력)

## 상호작용 흐름
1. 사용자가 질의를 입력하고 "분석 시작" 클릭
2. 시작 API 호출 → thread_id 수신
3. SSE 구독 시작 → 노드별 이벤트 카드 추가
4. orchestrator/final 이벤트 도착 시 최종 결과 섹션 하이라이트
5. 오류 이벤트 수신 시 명시적 fallback 배지 + 재시도 버튼 노출

## 시각 언어
- Finance Analyst: Blue accent
- Risk Compliance: Red accent
- Orchestrator: Purple accent
- System/Fallback: Amber accent
- 접근성: 대비비율 4.5:1 이상, 키보드 포커스 링 제공

## 품질 지표
- TTFU(Time To First Update): < 2s
- 분석 시작→최종 결론: < 20s (mock 기준)
- 오류 시 사용자 인지 시간: < 1s
- 로그/결론 이해도(사용자 테스트): 80%+

## 저장소 내 구현 연결
- `frontend_prototype/index.html`: 2-pane 실동작 프로토타입
- `frontend_prototype/README.md`: 로컬 실행/연동 방법
- `10_Real_Integration_Playbook.md`: 실제 연동(사람 수행) 절차
