# Frontend Prototype Usage

## 1) Backend 실행
- FastAPI 설치 후 서버 실행
- `uvicorn app.main:app --reload --port 8000`

## 2) Prototype 열기
- 브라우저로 `frontend_prototype/index.html` 파일을 열거나 간단한 정적 서버 사용:
- `python -m http.server 5500`
- 접속: `http://localhost:5500/frontend_prototype/index.html`

## 3) 동작
- 질의 입력 후 "분석 시작" 클릭
- 좌측: 노드별 실시간 로그
- 우측: 재무/리스크/최종 결론 요약 + 타임라인
