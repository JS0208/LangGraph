# 수동 작업 체크리스트

## 1. 패키지 설치

```bash
pip install -r requirements.txt
pip install sentence-transformers aiosqlite
```

---

## 2. .env 파일 생성

```bash
cp .env.example .env
```

`.env` 열어서 아래 5개 값 채우기:

```
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
QDRANT_URL=
QDRANT_API_KEY=
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=
CHECKPOINTER_DSN=sqlite:///./checkpoints.db
```

---

## 3. Qdrant 인덱스 생성

아래 스크립트 실행 (URL·키는 .env와 동일하게):

```python
from qdrant_client import QdrantClient
client = QdrantClient(url="https://...", api_key="...")
client.create_payload_index("financial_docs", "company_name", "keyword")
client.create_payload_index("financial_docs", "year", "integer")
```

```bash
pip install qdrant-client
python create_qdrant_index.py
```

---

## 4. 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

정상 확인:
```bash
curl http://localhost:8000/api/v1/analyze/health
```

---

## 5. (선택) RAGAS 정밀 평가

```bash
pip install ragas datasets
python eval/run_eval.py --ragas
```

---

끝.
