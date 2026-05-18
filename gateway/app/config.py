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


settings = Settings()
