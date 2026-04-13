# Frontend Prototype Usage

이 디렉터리는 빠른 시연용 정적 HTML 프로토타입입니다.
정식 프론트엔드는 `../frontend_app/`에 있으며, 이 문서는 프로토타입 전용 실행법만 다룹니다.

## 1) 백엔드 실행

```bash
uvicorn app.main:app --reload --port 8000
```

## 2) 프로토타입 열기

간단한 정적 서버를 루트 디렉터리에서 실행합니다.

```bash
python -m http.server 5500
```

접속 주소:

```text
http://localhost:5500/frontend_prototype/index.html
```

## 3) 동작

- 질의 입력 후 "분석 시작" 클릭
- 좌측: 노드별 실시간 로그
- 우측: 재무/리스크/최종 결론 요약과 타임라인

## 참고

- API 기본 주소는 `http://localhost:8000`을 가정합니다.
- `python app/main.py`는 API 서버가 아니라 콘솔 데모이므로, 프로토타입 연동에는 `uvicorn` 실행을 사용해야 합니다.
