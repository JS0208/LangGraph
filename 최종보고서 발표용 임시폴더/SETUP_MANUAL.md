# GraphRAG — 직접 해야 하는 설정 가이드

> **이 파일은 8개 개선 항목 구현 완료 후, 실제 실행을 위해 지성님이 직접 해야 하는 모든 작업을 단계별로 정리한 문서입니다.**
>
> 코드는 전부 완성되어 있습니다. 아래 항목들은 코드 밖에 있는 환경·인프라·인증 설정이라 자동화할 수 없습니다.

---

## 목차

1. [패키지 설치](#1-패키지-설치)
2. [환경변수 설정 (.env)](#2-환경변수-설정)
3. [Qdrant payload 인덱스 생성](#3-qdrant-payload-인덱스-생성)
4. [체크포인터 저장소 선택 및 설정](#4-체크포인터-저장소-선택-및-설정)
5. [LangGraph Interrupt 설정 (선택)](#5-langgraph-interrupt-설정)
6. [Cross-Encoder 모델 사전 다운로드 (선택)](#6-cross-encoder-모델-사전-다운로드)
7. [프롬프트 런타임 오버라이드 (선택)](#7-프롬프트-런타임-오버라이드)
8. [서버 기동 확인](#8-서버-기동-확인)

---

## 1. 패키지 설치

### 1-A. 기존 패키지 (이미 있어야 함)

```bash
pip install -r requirements.txt
```

`requirements.txt`에 이미 포함된 핵심 패키지:
- `langgraph>=0.2` — 그래프 실행 엔진
- `fastapi`, `uvicorn`, `pydantic`, `httpx`
- `neo4j>=5.23`
- `python-dotenv`

### 1-B. 신규 추가 패키지 (반드시 설치)

```bash
# Cross-Encoder 재랭킹 (항목 2 — BM25 + 반대의미 오검색 방지)
pip install sentence-transformers

# Checkpointer 영속화 중 하나를 선택해서 설치 (항목 1)
pip install aiosqlite          # 로컬 개발 / 단일 서버 → SQLite 선택 시
# 또는
pip install psycopg[binary]    # 프로덕션 / 멀티 서버 → PostgreSQL 선택 시
```

> **참고:** `sentence-transformers`를 설치하지 않아도 서버는 정상 기동됩니다.
> 미설치 시 Cross-Encoder 재랭킹이 자동으로 비활성화되고, BM25 hybrid 재랭킹만 동작합니다.

### 1-C. `requirements.txt`에 추가 권장

나중에 다른 환경에서 재설치할 때를 위해 직접 파일에 추가해 두세요:

```
# Sprint 7/8 additions
sentence-transformers>=3.0
aiosqlite>=0.20          # SQLite checkpointer 사용 시
# psycopg[binary]>=3.2   # PostgreSQL checkpointer 사용 시
```

---

## 2. 환경변수 설정

### 2-A. `.env` 파일 생성

```bash
cd LangGraph-main   # 프로젝트 루트
cp .env.example .env
```

### 2-B. 필수 항목 (비어 있으면 실제 LLM/검색 불가)

`.env` 파일을 열어서 아래 값들을 실제 값으로 교체하세요:

```dotenv
# ── LLM ──────────────────────────────────────────────────────────────────────
# Google Gemini 사용 시
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=<Google AI Studio API 키>
LLM_MODEL=gemini-2.0-flash

# OpenAI 사용 시
# LLM_BASE_URL=https://api.openai.com/v1/chat/completions
# LLM_API_KEY=sk-...
# LLM_MODEL=gpt-4o

# ── Qdrant (벡터 DB) ──────────────────────────────────────────────────────────
QDRANT_URL=https://<your-cluster-id>.us-east4-0.gcp.cloud.qdrant.io
QDRANT_API_KEY=<Qdrant API 키>
QDRANT_COLLECTION=financial_docs

# ── Neo4j (그래프 DB) ─────────────────────────────────────────────────────────
NEO4J_URI=bolt+s://<your-neo4j-host>:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<패스워드>

# ── DART ─────────────────────────────────────────────────────────────────────
DART_API_KEY=<DART Open API 키>  # https://opendart.fss.or.kr 에서 발급
```

### 2-C. 신규 항목 (항목 1~4 관련)

```dotenv
# 체크포인터 저장소 (아래 "4번 섹션" 참고)
CHECKPOINTER_DSN=sqlite:///./checkpoints.db

# Cross-Encoder 모델명 (기본값 그대로 유지 권장)
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# Interrupt 지점 (필요 시만 설정 — 기본 비활성화)
GRAPH_INTERRUPT_BEFORE=
GRAPH_INTERRUPT_AFTER=

# 적응형 Neo4j hop (기본 활성화)
ADAPTIVE_HOP_ENABLED=1

# 프롬프트 오버라이드 디렉토리 (선택)
PROMPT_OVERRIDE_DIR=
```

### 2-D. 개발/테스트 시 fallback 모드로 빠른 실행

외부 서비스(Qdrant, Neo4j, LLM) 없이 seed 데이터로만 테스트하려면:

```dotenv
RETRIEVAL_FORCE_FALLBACK=1
# LLM_API_KEY 비워두면 heuristic fallback으로 동작
```

---

## 3. Qdrant payload 인덱스 생성

**왜 필요한가?** `company_name`과 `year` 필드로 필터링할 때 인덱스가 없으면 Qdrant가 400 에러를 반환합니다. 코드에 자동 fallback이 있지만, 인덱스가 있어야 정확한 필터 검색이 됩니다.

### 방법 A — Python 스크립트 (권장)

```python
from qdrant_client import QdrantClient

client = QdrantClient(
    url="https://<your-cluster>.qdrant.io",
    api_key="<your-api-key>",
)
collection = "financial_docs"

# company_name 인덱스
client.create_payload_index(
    collection_name=collection,
    field_name="company_name",
    field_schema="keyword",
)

# year 인덱스
client.create_payload_index(
    collection_name=collection,
    field_name="year",
    field_schema="integer",
)

print("인덱스 생성 완료")
```

실행:
```bash
pip install qdrant-client
python create_qdrant_index.py   # 위 코드를 파일로 저장 후 실행
```

### 방법 B — curl (REST API 직접 호출)

```bash
QDRANT_URL="https://<your-cluster>.qdrant.io"
QDRANT_KEY="<your-api-key>"
COLLECTION="financial_docs"

# company_name 인덱스
curl -X PUT "$QDRANT_URL/collections/$COLLECTION/index" \
  -H "api-key: $QDRANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "company_name", "field_schema": "keyword"}'

# year 인덱스
curl -X PUT "$QDRANT_URL/collections/$COLLECTION/index" \
  -H "api-key: $QDRANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "year", "field_schema": "integer"}'
```

### 방법 C — Docker로 Qdrant 로컬 실행 시

```bash
docker compose --profile infra up qdrant -d
# 컨테이너 기동 후 위 Python 스크립트에서
# url="http://localhost:6333", api_key="" 로 실행
```

---

## 4. 체크포인터 저장소 선택 및 설정

그래프 실행 중단/재개(interrupt/resume) 기능을 위해 체크포인트를 영속화할 저장소를 설정합니다.

### 옵션 A — SQLite (로컬 개발 / 단일 서버 권장)

```bash
pip install aiosqlite
```

`.env`:
```dotenv
CHECKPOINTER_DSN=sqlite:///./checkpoints.db
```

- 프로세스 재시작 후에도 중단된 그래프 상태 복원 가능
- 파일 위치: 프로젝트 루트의 `checkpoints.db`
- 별도 DB 서버 불필요, 즉시 사용 가능

### 옵션 B — PostgreSQL (프로덕션 / 멀티 서버)

```bash
pip install psycopg[binary]
```

`.env`:
```dotenv
CHECKPOINTER_DSN=postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag
```

Docker로 Postgres 실행:
```bash
docker compose --profile infra up postgres -d
```

> PostgreSQL 사용 시 LangGraph가 첫 실행 때 `checkpoints` 테이블을 자동 생성합니다.
> DB 유저에게 `CREATE TABLE` 권한이 필요합니다.

### 옵션 C — 미설정 (MemorySaver — 개발 초기)

`.env`:
```dotenv
CHECKPOINTER_DSN=   # 비워두기
```

- 프로세스가 살아있는 동안만 상태 유지
- 재시작 시 모든 체크포인트 소멸
- interrupt/resume 기능은 동작하지만 서버 재시작 시 상태 소멸

---

## 5. LangGraph Interrupt 설정

**Human-in-the-Loop**: 특정 노드 실행 전후에 그래프를 일시정지하고, 사람이 확인 후 `/api/v1/analyze/resume/{thread_id}`로 재개하는 패턴입니다.

### 설정 방법

`.env`에 interrupt 지점을 지정합니다:

```dotenv
# 검색 실행 전에 쿼리 플랜을 사람이 검토하고 승인
GRAPH_INTERRUPT_BEFORE=retrieve_context

# 여러 지점 지정 시 쉼표로 구분 (공백 없이)
# GRAPH_INTERRUPT_BEFORE=retrieve_context,evaluation
```

### 사용 가능한 노드 목록

| 노드명 | 의미 | interrupt 용도 |
|--------|------|----------------|
| `input_guardrails` | 입력 안전 검사 | 차단 전 수동 확인 |
| `intent_classifier` | 의도 분류 | 분류 결과 수정 |
| `retrieve_context` | 검색 실행 | 쿼리 플랜 검토 후 승인 |
| `finance_analyst` | 재무 분석 | 분석 시작 전 데이터 확인 |
| `evaluation` | LLM 평가 | 평가 결과 보고 후 승인 |

### resume API 호출 예시

```bash
# interrupt 발생 후 재개
curl -X POST "http://localhost:8000/api/v1/analyze/resume/{thread_id}" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": null,
    "target_company": "삼성전자",
    "target_year": 2024,
    "extra": null
  }'
```

> **주의:** Interrupt 기능은 `CHECKPOINTER_DSN`이 설정되어 있어야 정상 동작합니다.
> 체크포인터 없이 interrupt를 설정하면 상태 복원이 불가능합니다.

---

## 6. Cross-Encoder 모델 사전 다운로드

`sentence-transformers` 설치 후 처음 실행 시 모델 파일(약 90MB)을 자동으로 다운로드합니다.

### 인터넷이 자유로운 환경

자동 다운로드되므로 추가 작업 불필요. 첫 재랭킹 요청 시 30초 정도 지연이 있을 수 있습니다.

### 인터넷이 제한된 환경 (사내망, 서버 등)

개발 머신에서 미리 다운로드해 두세요:

```bash
python -c "
from sentence_transformers import CrossEncoder
model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
print('모델 캐시 완료 — 위치:', model.model.config._name_or_path)
"
```

캐시 위치: `~/.cache/huggingface/hub/`

서버에 복사하거나, 환경변수로 캐시 경로를 지정할 수 있습니다:
```dotenv
TRANSFORMERS_CACHE=/path/to/model/cache
```

### 모델 변경 시

한국어 금융 텍스트에 특화된 모델로 교체하고 싶다면:
```dotenv
CROSS_ENCODER_MODEL=Dongjin-kr/ko-reranker
```
단, `sentence-transformers` 호환 모델이어야 합니다.

---

## 7. 프롬프트 런타임 오버라이드

서버 재배포 없이 프롬프트(지시문)를 교체하는 기능입니다.

### 설정 방법

```dotenv
PROMPT_OVERRIDE_DIR=/etc/graphrag/prompts    # 원하는 디렉토리 경로
```

### 사용 방법

오버라이드할 프롬프트의 파일명은 반드시 기존 템플릿명과 동일해야 합니다:

```
/etc/graphrag/prompts/
├── finance_metrics.yaml       # 재무 분석 프롬프트 교체
├── risk_points.yaml           # 리스크 분석 프롬프트 교체
├── query_planner.yaml         # 쿼리 플래너 프롬프트 교체
├── evaluation_judge.yaml      # 평가 판사 프롬프트 교체
└── sufficiency_judge.yaml     # 충분성 판단 프롬프트 교체
```

### 파일 형식 (YAML front-matter + 프롬프트 본문)

```yaml
---
name: finance_metrics
version: "2.0.0"
description: "커스텀 재무 분석 프롬프트"
---
당신은 한국 상장사 전문 재무 분석가입니다.
아래 analysis_context를 바탕으로 분석하세요.

[커스텀 지시 추가]

analysis_context: {{ analysis_context }}
```

> `{{ analysis_context }}`, `{{ user_query }}` 등 `{{ }}` 변수 플레이스홀더는 반드시 유지해야 합니다.

### 교체 후 캐시 무효화 (서버 재시작 없이)

현재는 서버 재시작이 필요합니다. 무중단 교체가 필요하다면:
```python
from app.prompts import get_registry
get_registry.cache_clear()    # lru_cache 초기화
```

---

## 8. 서버 기동 확인

### 로컬 실행

```bash
cd LangGraph-main
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Compose (fallback 모드 — 외부 서비스 없이)

```bash
docker compose up backend
```

### Docker Compose (실제 인프라 포함)

```bash
docker compose --profile infra up
```
Qdrant, Neo4j, PostgreSQL, Redis가 모두 로컬 컨테이너로 실행됩니다.

### 기동 확인 체크리스트

```bash
# 1. health check
curl http://localhost:8000/api/v1/analyze/health
# 기대: {"status":"ok","ts":...}

# 2. fallback 모드 동작 확인 (외부 서비스 없이)
curl -X POST http://localhost:8000/api/v1/analyze/start \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"query": "삼성전자 2024년 부채비율 알려줘"}'
# 기대: {"status":"started","thread_id":"..."}

# 3. 스트리밍 확인
curl -N http://localhost:8000/api/v1/analyze/stream/{thread_id} \
  -H "Authorization: Bearer test-token"
# 기대: SSE 이벤트 스트림 (node_start, node_end, done 이벤트)
```

---

## 요약 — 최소 시작 체크리스트

| 순서 | 작업 | 필수 여부 |
|------|------|-----------|
| ① | `pip install -r requirements.txt` | 🔴 필수 |
| ② | `pip install sentence-transformers aiosqlite` | 🔴 필수 (Cross-Encoder + SQLite checkpointer) |
| ③ | `cp .env.example .env` 후 LLM/Qdrant/Neo4j 키 입력 | 🔴 필수 (실제 검색 사용 시) |
| ④ | `.env`에 `CHECKPOINTER_DSN=sqlite:///./checkpoints.db` 추가 | 🟡 권장 |
| ⑤ | Qdrant `company_name`, `year` payload 인덱스 생성 | 🟡 권장 (필터 검색 정확도) |
| ⑥ | Cross-Encoder 모델 사전 다운로드 (인터넷 제한 환경만) | 🔵 선택 |
| ⑦ | `GRAPH_INTERRUPT_BEFORE` 설정 (Human-in-the-Loop 필요 시) | 🔵 선택 |
| ⑧ | `PROMPT_OVERRIDE_DIR` 설정 (프롬프트 핫스왑 필요 시) | 🔵 선택 |

---

*이 문서는 GraphRAG Sprint 7/8 구현 완료 기준으로 작성되었습니다.*
