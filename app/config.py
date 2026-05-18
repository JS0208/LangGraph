from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # 이 함수가 명시적으로 호출되어야 함


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = os.getenv("NEO4J_URI", "")
    neo4j_user: str = os.getenv("NEO4J_USER", "")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "financial_docs")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    # Qdrant/Neo4j URL 이 .env 에 남아 있어도 서비스가 꺼진 경우 빠르게 시드 폴백만 쓰려면 1.
    retrieval_force_fallback: bool = field(default_factory=lambda: _truthy_env("RETRIEVAL_FORCE_FALLBACK"))

    @property
    def has_real_retrieval(self) -> bool:
        return bool(
            self.neo4j_uri
            and self.neo4j_user
            and self.neo4j_password
            and self.qdrant_url
            and self.qdrant_api_key
        )

    @property
    def use_real_retrieval(self) -> bool:
        """실 Qdrant/Neo4j 경로 사용 여부 — 자격 증명 + 강제 폴백 비활성."""
        if self.retrieval_force_fallback:
            return False
        return self.has_real_retrieval

    @property
    def has_real_llm(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)


settings = Settings()
