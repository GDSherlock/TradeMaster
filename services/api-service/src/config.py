from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVICE_ROOT.parents[1]
ENV_FILE = PROJECT_ROOT / "config" / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("API_SERVICE_HOST", "0.0.0.0")
    port: int = _int("API_SERVICE_PORT", 8000)
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/market_data")
    default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance_futures_um")

    auth_enabled: bool = _bool("AUTH_ENABLED", False)
    api_token: str = os.getenv("API_TOKEN", "dev-token")

    cors_allow_origins: list[str] = None  # type: ignore[assignment]
    rate_limit_per_minute: int = _int("API_RATE_LIMIT_PER_MINUTE", 120)
    rate_limit_burst: int = _int("API_RATE_LIMIT_BURST", 20)

    def __post_init__(self) -> None:
        origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8088")
        object.__setattr__(self, "cors_allow_origins", [x.strip() for x in origins.split(",") if x.strip()])


settings = Settings()
