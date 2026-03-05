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


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("SIGNAL_SERVICE_HOST", "0.0.0.0")
    port: int = _int("SIGNAL_SERVICE_PORT", 8002)

    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/market_data")
    default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance_futures_um")

    auth_enabled: bool = _bool("AUTH_ENABLED", False)
    api_token: str = os.getenv("API_TOKEN", "dev-token")

    cors_allow_origins: list[str] = None  # type: ignore[assignment]
    rate_limit_per_minute: int = _int("SIGNAL_RATE_LIMIT_PER_MINUTE", 120)
    rate_limit_burst: int = _int("SIGNAL_RATE_LIMIT_BURST", 20)

    schedule_seconds: int = _int("SIGNAL_SCHEDULE_SECONDS", 30)
    ws_poll_seconds: float = _float("SIGNAL_WS_POLL_SECONDS", 1.0)

    symbols: list[str] = None  # type: ignore[assignment]
    intervals: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8088")
        object.__setattr__(self, "cors_allow_origins", [x.strip() for x in origins.split(",") if x.strip()])
        object.__setattr__(self, "symbols", [x.upper() for x in _csv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")])
        object.__setattr__(self, "intervals", [x.lower() for x in _csv("INTERVALS", "1m,5m,15m,1h,4h,1d")])


settings = Settings()
