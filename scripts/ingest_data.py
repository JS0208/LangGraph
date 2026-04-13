from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List

import httpx
from app.config import settings

# 의존성 확인
try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    raise RuntimeError("neo4j package is missing. Run: pip install neo4j")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Gemini(text-embedding-004) 기준 차원 수 (OpenAI 호환 시 1536으로 변경)
VECTOR_SIZE = 768


async def get_embedding(text: str, client: httpx.AsyncClient) -> List[float]:
    """
    LLM Provider를 식별하여 텍스트 임베딩을 생성합니다. (Gemini 지원 추가)
    """
    if not settings.llm_base_url or not settings.llm_api_key:
        logger.warning("LLM API 설정 누락. 더미 임베딩 반환.")
        return [0.0] * VECTOR_SIZE

    is_gemini = "generativelanguage.googleapis.com" in settings.llm_base_url

    try:
        if is_gemini:
            # Gemini 임베딩 규격
            url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-001:embedContent?key={settings.llm_api_key}"
            payload = {
                "model": "models/text-embedding-001",
                "content": {"parts": [{"text": text}]}
            }
            response = await client.post(url, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            return data["embedding"]["values"]
            
        else:
            # OpenAI 호환 규격
            url = settings.llm_base_url.replace("/chat/completions", "/embeddings")
            headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
            payload = {
                "input": text,
                "model": "text-embedding-3-small"
            }
            response = await client.post(url, headers=headers, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
            
    except Exception as e:
        logger.error(f"임베딩 생성 실패: {e}")
        return [0.0] * VECTOR_SIZE


async def setup_qdrant_collection(client: httpx.AsyncClient) -> None:
    """Qdrant 컬렉션을 768차원(Gemini 기준)으로 초기화 및 재생성합니다."""
    url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}"
    headers = {"api-key": settings.qdrant_api_key}

    # 기존 컬렉션 존재 여부 확인 및 삭제 (차원 수 변경 및 더미 데이터 초기화를 위함)
    resp = await client.get(url, headers=headers)
    if resp.status_code == 200:
        logger.warning(f"기존 Qdrant 컬렉션 '{settings.qdrant_collection}'을(를) 삭제하고 재구성합니다.")
        delete_resp = await client.delete(url, headers=headers)
        delete_resp.raise_for_status()

    # 컬렉션 신규 생성
    payload = {
        "vectors": {
            "size": VECTOR_SIZE,
            "distance": "Cosine"
        }
    }
    create_resp = await client.put(url, headers=headers, json=payload)
    create_resp.raise_for_status()
    logger.info(f"Qdrant 컬렉션 '{settings.qdrant_collection}' ({VECTOR_SIZE}차원) 생성 완료.")


async def ingest_to_qdrant(data: Dict[str, Any], client: httpx.AsyncClient) -> None:
    """텍스트를 임베딩하여 메타데이터와 함께 Qdrant에 Upsert 합니다."""
    url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/points"
    headers = {"api-key": settings.qdrant_api_key}

    points = []
    for company in data.get("companies", []):
        name = company.get("name")
        year = company.get("year")
        
        financial_text = (
            f"{name}의 {year}년 {company.get('quarter')} 재무 실적: "
            f"매출 {company.get('revenue')}억원, 영업이익 {company.get('operating_profit')}억원, "
            f"부채비율 {company.get('debt_ratio')}%."
        )
        fin_emb = await get_embedding(financial_text, client)
        points.append({
            "id": str(uuid.uuid4()),
            "vector": fin_emb,
            "payload": {
                "source_type": "FINANCIAL_REPORT",
                "company_name": name,
                "year": year,
                "text_content": financial_text
            }
        })

        for disc in company.get("disclosures", []):
            disc_text = f"{name} {disc.get('date')} 공시 ({disc.get('event_type')}): {disc.get('summary')}"
            disc_emb = await get_embedding(disc_text, client)
            points.append({
                "id": str(uuid.uuid4()),
                "vector": disc_emb,
                "payload": {
                    "source_type": "DISCLOSURE",
                    "company_name": name,
                    "year": year,
                    "text_content": disc_text
                }
            })

    if not points:
        return

    payload = {"points": points}
    resp = await client.put(url, headers=headers, json=payload)
    resp.raise_for_status()
    logger.info(f"Qdrant에 {len(points)}개의 벡터 포인트 정상 적재 완료.")


async def ingest_to_neo4j(data: Dict[str, Any]) -> None:
    """Cypher 쿼리를 통해 Neo4j에 노드와 엣지를 병합(MERGE) 합니다."""
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, 
        auth=(settings.neo4j_user, settings.neo4j_password)
    )

    query = """
    UNWIND $companies AS comp
    
    MERGE (c:Company {name: comp.name})
    
    MERGE (r:FinancialReport {id: comp.name + "_" + toString(comp.year) + "_" + comp.quarter})
    SET r.year = comp.year,
        r.quarter = comp.quarter,
        r.revenue = comp.revenue,
        r.operating_profit = comp.operating_profit,
        r.debt_ratio = comp.debt_ratio
    MERGE (c)-[:HAS_REPORT]->(r)
    
    WITH c, comp
    UNWIND comp.disclosures AS disc
    MERGE (d:Disclosure {id: comp.name + "_" + disc.date + "_" + disc.event_type})
    SET d.date = disc.date,
        d.event_type = disc.event_type,
        d.summary = disc.summary
    MERGE (c)-[:INVOLVED_IN]->(d)
    """

    try:
        async with driver.session() as session:
            await session.run(query, companies=data.get("companies", []))
            logger.info("Neo4j에 지식 그래프 노드 및 엣지 정상 적재 완료.")
    except Exception as e:
        logger.error(f"Neo4j 적재 실패: {e}")
        raise
    finally:
        await driver.close()


async def main() -> None:
    logger.info("데이터 적재 파이프라인을 시작합니다 (Gemini API 감지 모드)...")
    
    if not settings.has_real_retrieval:
        logger.error("환경 변수(.env) 불일치. 실행 중단.")
        return

    seed_path = Path("tests/seed_data/mock_dart_response.json")
    if not seed_path.exists():
        logger.error(f"Seed 파일 누락: {seed_path}")
        return
        
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    async with httpx.AsyncClient() as client:
        try:
            await setup_qdrant_collection(client)
            await asyncio.gather(
                ingest_to_qdrant(data, client),
                ingest_to_neo4j(data)
            )
            logger.info("모든 데이터베이스 적재 완료. 이제 실제 검색이 동작합니다.")
            
        except Exception as e:
            logger.error(f"파이프라인 실행 중 오류: {e}")

if __name__ == "__main__":
    asyncio.run(main())