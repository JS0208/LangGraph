from __future__ import annotations

import asyncio
import os
import uuid
import logging
import re
import sys
from pathlib import Path
from datetime import date
from typing import Any, Dict, List

import httpx
import OpenDartReader
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    raise RuntimeError("neo4j package is missing. Run: pip install neo4j")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

VECTOR_SIZE = 768
TODAY = date.today()
CURRENT_YEAR = TODAY.year

# DART API는 한글 이름 탐색 시 충돌이 발생하므로, 상장 종목코드(6자리)를 직접 매핑하여 무결성을 확보합니다.
TARGET_COMPANIES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "064400": "LG CNS",
}
TARGET_YEARS = ["2023", "2024", "2025", "2026"]
MAX_DISCLOSURES_PER_YEAR = 5
DISCLOSURE_PRIORITY_KEYWORDS = [
    "규제",
    "소송",
    "계약",
    "투자",
    "유상증자",
    "무상증자",
    "감자",
    "전환사채",
    "신주",
    "인수",
    "합병",
    "분할",
    "자회사",
    "영업양수도",
    "횡령",
    "배임",
]

# DART API 인증
DART_KEY = os.getenv("DART_API_KEY")
if not DART_KEY:
    raise SystemExit("[FAIL] .env 파일에 DART_API_KEY가 없습니다.")
dart = OpenDartReader(DART_KEY)


def parse_dart_amount(val: Any) -> float:
    """DART의 비정형 텍스트 금액(콤마, -, 공백)을 안전하게 Float으로 변환"""
    if not val:
        return 0.0
    if isinstance(val, str):
        val = re.sub(r'[^0-9.-]', '', val)
        if not val or val == '-':
            return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def report_window(year: str) -> tuple[str, str]:
    start = f"{year}0101"
    if int(year) < CURRENT_YEAR:
        return start, f"{year}1231"
    return start, TODAY.strftime("%Y%m%d")


def period_label(year: str) -> str:
    return "FY" if int(year) < CURRENT_YEAR else "YTD"


def disclosure_priority(summary: str) -> int:
    return sum(1 for keyword in DISCLOSURE_PRIORITY_KEYWORDS if keyword in summary)


def classify_event(summary: str) -> str:
    for keyword in DISCLOSURE_PRIORITY_KEYWORDS:
        if keyword in summary:
            return keyword
    return "주요공시"


def select_disclosures(reports: pd.DataFrame) -> list[dict[str, str]]:
    if not isinstance(reports, pd.DataFrame) or reports.empty:
        return []

    candidates: list[dict[str, str | int]] = []
    for _, row in reports.iterrows():
        summary = str(row.get("report_nm", "")).strip()
        if not summary:
            continue
        candidates.append(
            {
                "date": str(row.get("rcept_dt", "")),
                "summary": summary,
                "score": disclosure_priority(summary),
                "event_type": classify_event(summary),
            }
        )

    if not candidates:
        return []

    prioritized = [item for item in candidates if int(item["score"]) > 0]
    selected_pool = prioritized or candidates
    selected_pool.sort(key=lambda item: (int(item["score"]), str(item["date"])), reverse=True)

    return [
        {
            "date": str(item["date"]),
            "event_type": str(item["event_type"]),
            "summary": str(item["summary"]),
        }
        for item in selected_pool[:MAX_DISCLOSURES_PER_YEAR]
    ]


async def get_embedding(text: str, client: httpx.AsyncClient) -> List[float]:
    """2026년 현재 지원되는 최신 gemini-embedding-001 모델로 강제 마이그레이션"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={settings.llm_api_key}"
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]}
    }
    resp = await client.post(url, json=payload, timeout=20.0)
    
    if resp.status_code != 200:
        logger.error(f"임베딩 실패: HTTP {resp.status_code} - {resp.text}")
        return [0.0] * VECTOR_SIZE

    values = resp.json()["embedding"]["values"]
    if len(values) >= VECTOR_SIZE:
        return values[:VECTOR_SIZE]
    return values + [0.0] * (VECTOR_SIZE - len(values))


def fetch_real_dart_data(corp_code: str, company_name: str, year: str) -> Dict[str, Any]:
    logger.info(f"[{company_name}][{year}] DART 데이터 크롤링 시작...")
    company_data = {
        "name": company_name,
        "year": int(year),
        "quarter": period_label(year),
        "revenue": 0,
        "operating_profit": 0,
        "debt_ratio": 0.0,
        "disclosures": [],
        "has_financial_data": False,
        "data_quality_flags": [],
    }

    # 1. 연도별 핵심 재무 추출
    try:
        fin = dart.finstate_all(corp_code, year)
        if isinstance(fin, pd.DataFrame) and not fin.empty:
            rev_mask = fin['account_nm'].isin(['매출액', '수익(매출액)', '영업수익'])
            prof_mask = fin['account_nm'].isin(['영업이익(손실)', '영업이익'])
            ast_mask = fin['account_nm'].isin(['자산총계'])
            liab_mask = fin['account_nm'].isin(['부채총계'])

            revenue_row = fin.loc[rev_mask]
            profit_row = fin.loc[prof_mask]
            assets_row = fin.loc[ast_mask]
            liabilities_row = fin.loc[liab_mask]
            company_data["has_financial_data"] = True

            if not revenue_row.empty:
                company_data["revenue"] = int(parse_dart_amount(revenue_row.iloc[0]['thstrm_amount']) / 100000000)
            else:
                company_data["data_quality_flags"].append("revenue_missing")
            if not profit_row.empty:
                company_data["operating_profit"] = int(parse_dart_amount(profit_row.iloc[0]['thstrm_amount']) / 100000000)
            else:
                company_data["data_quality_flags"].append("operating_profit_missing")
            
            if not assets_row.empty and not liabilities_row.empty:
                liabilities = parse_dart_amount(liabilities_row.iloc[0]['thstrm_amount'])
                assets = parse_dart_amount(assets_row.iloc[0]['thstrm_amount'])
                equity = assets - liabilities
                if equity > 0:
                    company_data["debt_ratio"] = round((liabilities / equity) * 100, 2)
                else:
                    company_data["data_quality_flags"].append("debt_ratio_unavailable")
            else:
                company_data["data_quality_flags"].append("debt_ratio_missing")
        else:
            logger.warning(f"[{company_name}][{year}] DART에서 재무제표를 반환하지 않았습니다.")
            company_data["data_quality_flags"].append("financial_statement_empty")
    except Exception as e:
        logger.warning(f"[{company_name}][{year}] 재무 파싱 실패: {e}")
        company_data["data_quality_flags"].append("financial_parse_failed")

    # 2. 연도별 중요 공시 선별
    try:
        start_date, end_date = report_window(year)
        reports = dart.list(corp_code, start=start_date, end=end_date, final=False)
        company_data["disclosures"] = select_disclosures(reports)
        if not company_data["disclosures"]:
            company_data["data_quality_flags"].append("disclosure_not_found")
    except Exception as e:
        logger.warning(f"[{company_name}][{year}] 공시 파싱 실패: {e}")
        company_data["data_quality_flags"].append("disclosure_parse_failed")

    if int(year) == CURRENT_YEAR:
        company_data["data_quality_flags"].append("current_year_partial_data")

    logger.info(
        f"[{company_name}][{year}] 추출 성공 | 매출: {company_data['revenue']}억, "
        f"부채비율: {company_data['debt_ratio']}% | 공시 {len(company_data['disclosures'])}건"
    )

    return company_data


async def ingest_to_qdrant(data_list: List[Dict], client: httpx.AsyncClient) -> None:
    url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/points"
    headers = {"api-key": settings.qdrant_api_key}
    points = []

    for comp in data_list:
        financial_text = f"{comp['name']}의 {comp['year']}년 {comp['quarter']} 재무 실적: 매출 {comp['revenue']}억원, 영업이익 {comp['operating_profit']}억원, 부채비율 {comp['debt_ratio']}%."
        fin_emb = await get_embedding(financial_text, client)
        points.append({
            "id": str(uuid.uuid4()),
            "vector": fin_emb,
            "payload": {
                "source_type": "FINANCIAL_REPORT",
                "company_name": comp['name'],
                "year": comp['year'],
                "quarter": comp["quarter"],
                "revenue": comp["revenue"],
                "operating_profit": comp["operating_profit"],
                "debt_ratio": comp["debt_ratio"],
                "has_financial_data": comp["has_financial_data"],
                "data_quality_flags": comp["data_quality_flags"],
                "text_content": financial_text,
            }
        })

        for disc in comp.get("disclosures", []):
            disc_text = f"{comp['name']} {disc['date']} 공시: {disc['summary']}"
            disc_emb = await get_embedding(disc_text, client)
            points.append({
                "id": str(uuid.uuid4()),
                "vector": disc_emb,
                "payload": {
                    "source_type": "DISCLOSURE",
                    "company_name": comp['name'],
                    "year": comp['year'],
                    "date": disc["date"],
                    "event_type": disc["event_type"],
                    "summary": disc["summary"],
                    "data_quality_flags": comp["data_quality_flags"],
                    "text_content": disc_text,
                }
            })

    if points:
        resp = await client.put(url, headers=headers, json={"points": points})
        resp.raise_for_status()
        logger.info(f"Qdrant에 {len(points)}개의 유효 벡터 적재 완료.")


async def ensure_qdrant_indexes(client: httpx.AsyncClient) -> None:
    base_url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/index"
    headers = {"api-key": settings.qdrant_api_key}
    index_specs = [
        {"field_name": "company_name", "field_schema": "keyword"},
        {"field_name": "year", "field_schema": "integer"},
        {"field_name": "source_type", "field_schema": "keyword"},
    ]

    for spec in index_specs:
        resp = await client.put(base_url, headers=headers, json=spec)
        resp.raise_for_status()
    logger.info("Qdrant payload index 생성/확인 완료.")


async def ingest_to_neo4j(data_list: List[Dict]) -> None:
    driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    query = """
    UNWIND $companies AS comp
    MERGE (c:Company {name: comp.name})
    MERGE (r:FinancialReport {id: comp.name + "_" + toString(comp.year) + "_" + comp.quarter})
    SET r.year = comp.year, r.revenue = comp.revenue, r.operating_profit = comp.operating_profit, r.debt_ratio = comp.debt_ratio
    MERGE (c)-[:HAS_REPORT]->(r)
    
    WITH c, comp
    UNWIND comp.disclosures AS disc
    MERGE (d:Disclosure {id: comp.name + "_" + disc.date + "_" + disc.summary})
    SET d.date = disc.date, d.summary = disc.summary
    MERGE (c)-[:INVOLVED_IN]->(d)
    """
    try:
        async with driver.session() as session:
            await session.run(query, companies=data_list)
            logger.info("Neo4j 지식 그래프 적재 완료.")
    finally:
        await driver.close()


async def main():
    logger.info("5개 핵심 기업 2023~2026 선별 적재 파이프라인 가동...")
    
    real_data_list = []
    for code, name in TARGET_COMPANIES.items():
        for year in TARGET_YEARS:
            data = fetch_real_dart_data(code, name, year)
            real_data_list.append(data)

    async with httpx.AsyncClient() as client:
        await ensure_qdrant_indexes(client)
        await asyncio.gather(
            ingest_to_qdrant(real_data_list, client),
            ingest_to_neo4j(real_data_list)
        )
    logger.info("선별 적재 파이프라인 관통 완료.")

if __name__ == "__main__":
    asyncio.run(main())