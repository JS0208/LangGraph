"""Ingestion 보강 — Sprint 7 (Pillar 5).

스코프 부담을 줄이기 위해 외부 워크플로우 엔진(Prefect/Airflow) 도입은 보류.
대신 ``app/ingest/`` 안에 다음을 모듈화한다.
- ``parallel``: asyncio.Semaphore 기반 병렬 임베딩 헬퍼
- ``watermark``: rcept_no 등 마지막 처리 시점 영속화 (sqlite)
- ``quality``: 결측·음수·0매출 등 quarantine 규칙
- ``lineage``: ingested_at / ingest_version / source_url 메타 강제
"""

from app.ingest.lineage import LineageMeta, attach_lineage, current_ingest_version
from app.ingest.parallel import bounded_gather, parallel_embed
from app.ingest.quality import QualityVerdict, evaluate_company_record
from app.ingest.watermark import WatermarkStore, get_watermark_store

__all__ = [
    "LineageMeta",
    "attach_lineage",
    "current_ingest_version",
    "bounded_gather",
    "parallel_embed",
    "QualityVerdict",
    "evaluate_company_record",
    "WatermarkStore",
    "get_watermark_store",
]
