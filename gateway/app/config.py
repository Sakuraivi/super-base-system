from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


@dataclass
class Settings:
    # LLM
    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "API_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic"
        )
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("API_KEY", "")
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL_NAME", "mimo-v2.5-pro")
    )
    model_light: str = field(
        default_factory=lambda: os.getenv("MODEL_LIGHT", "mimo-v2.5-pro")
    )

    # Intent Router
    intent_mode: str = field(
        default_factory=lambda: os.getenv("INTENT_MODE", "mock")
    )  # mock | cloud

    # Gateway
    host: str = field(
        default_factory=lambda: os.getenv("GATEWAY_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("GATEWAY_PORT", "8000"))
    )

    # Redis (optional)
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    # Module Registry
    modules_dir: str = field(
        default_factory=lambda: os.getenv(
            "MODULES_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "modules"),
        )
    )

    # PostgreSQL
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "")
    )

    # STM (Short-Term Memory)
    stm_window_size: int = field(
        default_factory=lambda: int(os.getenv("STM_WINDOW_SIZE", "10"))
    )
    stm_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("STM_MAX_TOKENS", "2000"))
    )
    stm_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("STM_TTL_SECONDS", "86400"))
    )

    # LTM (Long-Term Memory)
    ltm_embedding_dimension: int = field(
        default_factory=lambda: int(os.getenv("LTM_EMBEDDING_DIMENSION", "384"))
    )
    ltm_chunk_size: int = field(
        default_factory=lambda: int(os.getenv("LTM_CHUNK_SIZE", "512"))
    )
    ltm_chunk_overlap: int = field(
        default_factory=lambda: int(os.getenv("LTM_CHUNK_OVERLAP", "64"))
    )
    ltm_search_top_k: int = field(
        default_factory=lambda: int(os.getenv("LTM_SEARCH_TOP_K", "5"))
    )
    qdrant_host: str = field(
        default_factory=lambda: os.getenv("QDRANT_HOST", "localhost")
    )
    qdrant_port: int = field(
        default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333"))
    )


settings = Settings()
