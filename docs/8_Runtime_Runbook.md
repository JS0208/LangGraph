# 8. Runtime Runbook

## 목적

이 파일은 저장소의 현재 실행 기준을 설명하는 운영 메모입니다.
과거 다른 환경에서 작성된 `/workspace/...`, `git branch`, `PR` 기준 기록은 이 저장소의 현재 로컬 상태와 맞지 않아 제거했습니다.

## 실행 기준

### 백엔드

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 테스트

```bash
pytest -q
python scripts/preflight_check.py
python scripts/audit_project.py
```

### 프론트엔드

```bash
cd frontend_app
npm install
npm run dev
```

## 운영 메모

- `python app/main.py`는 API 서버가 아니라 CLI 데모입니다.
- 기본 경로는 seed fallback을 포함한 재현 가능한 데모 실행입니다.
- 실연동 검증 절차는 `10_Real_Integration_Playbook.md`를 기준으로 관리합니다.

## 연결 문서

- 현재 상태와 남은 작업: `6_Project_Status_and_Next_Steps.md`
- 진행 상태 요약: `7_Progress_Dashboard.md`
- 최근 작업 로그: `CURSOR_LOG.md`
