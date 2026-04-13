# CURSOR_LOG

## 최근 정비 내용

- 루트 `README.md`를 추가해 저장소 개요, 실행법, 환경 변수, 문서 인덱스를 정리했다.
- `frontend_app/README.md`, `frontend_prototype/README.md`를 실제 사용 방식에 맞게 교체했다.
- 설계 문서 `2_GraphRAG_Pipeline.md`, `3_LangGraph_Orchestration.md`, `4_Backend_API_and_SSE.md`, `5_Frontend_and_QA.md`의 깨진 경로와 오래된 설명을 최신 구현 기준으로 보정했다.
- 상태 문서 `6_Project_Status_and_Next_Steps.md`, `7_Progress_Dashboard.md`, `8_Runtime_Runbook.md`를 현재 워크스페이스 기준으로 재정렬했다.
- 루트 문서 파일명을 `번호_주제.md` 규칙으로 정리해 구조를 일관화했다.
- 실행 정합성 보강을 위해 의존성/환경 변수/검색 fallback 관련 코드와 문서를 함께 정리했다.

## 현재 리스크

1. 실 DB/LLM 경로는 데모 수준을 넘는 운영 검증이 아직 없다.
2. SSE 이벤트 스키마는 구현상 안정적이지만 계약 문서가 아직 없다.
3. 실데이터 적재 스크립트는 외부 서비스와 자격 증명에 의존하므로 실패 지점이 많다.

## 다음 우선 작업

1. 실연동 환경에서 `pytest`, API 스트리밍, 적재 스크립트를 통합 검증
2. SSE 이벤트 페이로드를 프론트엔드 계약 문서로 고정
3. 배포/시크릿/보안 스캔 절차를 CI 수준으로 정리
