# DART API 데이터 수집·저장 구조 복습 (코드 기반)

> 참조 파일: `scripts/real_ingest.py` | 작성일: 2026-05-18

---

## 1. 전체 파이프라인 한 줄 요약

> **DART API → OpenDartReader로 재무제표·공시 수집 → 전처리 → Gemini 임베딩 → Qdrant 저장 & Neo4j 그래프 구축**

---

## 2. 수집 대상 (코드에서 직접 확인)

```python
TARGET_COMPANIES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "064400": "LG CNS",
}
TARGET_YEARS = ["2023", "2024", "2025", "2026"]
```

- **종목코드(6자리)를 직접 지정한 이유**: DART API는 한글 회사명 검색 시 동명이인 충돌 발생 가능. 코드 매핑으로 무결성 확보.
- 연도별로 `dart.finstate_all(corp_code, year)` 호출하여 전체 재무제표 수집.

---

## 3. DART 재무 데이터 수집 방법

```python
import OpenDartReader
dart = OpenDartReader(DART_API_KEY)

# 재무제표 전체 항목 조회 (XBRL 파싱 결과를 DataFrame으로 반환)
fin = dart.finstate_all(corp_code, year)
```

### 주요 추출 항목

| account_nm (계정명) | 추출 값 | 변환 방법 |
|---------------------|---------|-----------|
| `매출액` / `수익(매출액)` | revenue | `thstrm_amount` ÷ 1억 → 억원 단위 |
| `영업이익(손실)` | operating_profit | 동일 |
| `자산총계` + `부채총계` | debt_ratio | (부채 ÷ 자본) × 100 |

### 비정형 금액 파싱 처리

```python
def parse_dart_amount(val) -> float:
    # 콤마, 공백, 대시(-)가 섞인 문자열 → float 변환
    val = re.sub(r'[^0-9.-]', '', str(val))
    return float(val) if val and val != '-' else 0.0
```

**DART API 응답의 금액은 `"1,234,567"` 형태의 문자열**이므로 반드시 정제가 필요.

---

## 4. 공시 데이터 수집 및 선별

```python
reports = dart.list(corp_code, start="20240101", end="20241231", final=False)
```

- `dart.list()`는 DART 전자공시 목록을 DataFrame으로 반환
- `report_nm` 컬럼에 공시 제목이 들어있음
- 핵심 공시만 선별: **우선순위 키워드** 포함 여부로 점수화

```python
DISCLOSURE_PRIORITY_KEYWORDS = [
    "규제", "소송", "계약", "투자", "유상증자", "인수", "합병", "횡령", "배임", ...
]
```

- 점수가 높은 순으로 **연도당 최대 5건**만 보관 → 노이즈 최소화

---

## 5. 저장 구조: Qdrant (벡터 DB)

### 저장되는 포인트 종류

**① 재무 보고서 포인트**
```python
text = f"{회사명}의 {연도}년 {분기} 재무 실적: 매출 {revenue}억원, ..."
vector = await get_embedding(text, client)  # Gemini API
payload = {
    "source_type": "FINANCIAL_REPORT",
    "company_name": "삼성전자",
    "year": 2024,
    "revenue": 790000,
    "debt_ratio": 34.2,
    "text_content": text,
    ...
}
```

**② 공시 포인트**
```python
text = f"{회사명} {날짜} 공시: {공시제목}"
vector = await get_embedding(text, client)
payload = {
    "source_type": "DISCLOSURE",
    "event_type": "REGULATION",
    "summary": "공시 요약",
    ...
}
```

### Payload 인덱스 (필터링 속도를 위해)
```python
# keyword 인덱스 → company_name 기반 필터
# integer 인덱스 → year 기반 필터
인덱스: company_name (keyword), year (integer), source_type (keyword)
```

---

## 6. 저장 구조: Neo4j (지식 그래프)

```cypher
MERGE (c:Company {name: "삼성전자"})
MERGE (r:FinancialReport {id: "삼성전자_2024_FY"})
SET r.year = 2024, r.revenue = 790000, ...
MERGE (c)-[:HAS_REPORT]->(r)

MERGE (d:Disclosure {id: "삼성전자_2024-10-08_..."})
SET d.date = "2024-10-08", d.summary = "..."
MERGE (c)-[:INVOLVED_IN]->(d)
```

- **노드**: `Company`, `FinancialReport`, `Disclosure`
- **엣지**: `HAS_REPORT`, `INVOLVED_IN`
- 조회 시: `neo4j_two_hop()` 함수로 연관 기업·자회사 관계까지 2-hop 탐색

---

## 7. 임베딩: Gemini embedding-001

```python
url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
payload = {
    "model": "models/gemini-embedding-001",
    "content": {"parts": [{"text": 텍스트}]}
}
# 반환값: 768차원 float list
```

- 벡터 차원: **768**
- 768보다 짧으면 0.0으로 패딩, 길면 슬라이싱

---

## 8. 병렬 처리 (`app/ingest/parallel.py`)

```python
# Semaphore로 동시 요청 제한 (concurrency=8)
await asyncio.gather(
    ingest_to_qdrant(real_data_list, client),  # Qdrant 적재
    ingest_to_neo4j(real_data_list)             # Neo4j 적재
)
```

Qdrant와 Neo4j 적재는 **asyncio.gather로 병렬** 실행. 임베딩 API 호출은 Semaphore로 동시 요청 수 제한 (API rate limit 준수).

---

## 9. 데이터 품질 관리 (`data_quality_flags`)

| 플래그 | 의미 |
|--------|------|
| `revenue_missing` | 매출 항목 없음 |
| `financial_parse_failed` | 재무제표 파싱 예외 |
| `debt_ratio_unavailable` | 자본이 0 이하 (계산 불가) |
| `disclosure_not_found` | 해당 연도 공시 없음 |
| `current_year_partial_data` | 현재 연도 → 부분 데이터 |

- 분석 파이프라인의 **critic 노드**가 이 플래그를 읽어 `disagreement_score` 산정
- LLM 프롬프트에도 주입되어 "데이터 부족 시 단정 금지" 지시

---

## 10. 면접 답변 예시

**Q: "DART API 자료를 어떤 형태로 내려받고 저장했나요?"**

> "OpenDartReader 라이브러리를 통해 종목코드 기준으로 `finstate_all()`과 `list()`를 호출하여 재무제표와 공시 목록을 pandas DataFrame으로 수집했습니다. 금액 데이터는 DART 특성상 콤마가 섞인 문자열로 오는 경우가 많아 정규식으로 전처리했고요. 이를 두 가지 형태로 저장했는데, 의미 기반 검색을 위해 Gemini 임베딩(768차원)으로 변환해 Qdrant에 적재하고, 기업 간 관계(자회사·연관 공시)는 Neo4j에 Company→FinancialReport→Disclosure 구조의 지식 그래프로 구축했습니다. 실제 검색 시에는 두 결과를 reranker로 통합해 하이브리드 RAG를 구성했습니다."
