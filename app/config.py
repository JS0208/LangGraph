from __future__ import annotations
from dotenv import load_dotenv
import os
from dataclasses import dataclass
load_dotenv() # 이 함수가 명시적으로 호출되어야 함

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
    def has_real_llm(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)


settings = Settings()
