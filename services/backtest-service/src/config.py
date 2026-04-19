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
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_weak_token(token: str) -> bool:
    normalized = token.strip().lower()
    return normalized in {
        "",
        "dev-token",
        "changeme",
        "change-me",
        "<change_me_strong_token>",
        "<change_me_token>",
        "<change_me>",
    }


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("BACKTEST_SERVICE_HOST", "0.0.0.0")
    port: int = _int("BACKTEST_SERVICE_PORT", 8004)

    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/market_data")
    default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance_futures_um")

    auth_enabled: bool = _bool("AUTH_ENABLED", True)
    api_token: str = os.getenv("API_TOKEN", "")

    cors_allow_origins: list[str] = None  # type: ignore[assignment]
    rate_limit_per_minute: int = _int("BACKTEST_RATE_LIMIT_PER_MINUTE", 60)
    rate_limit_burst: int = _int("BACKTEST_RATE_LIMIT_BURST", 20)
    write_rate_limit_per_minute: int = 10
    write_rate_limit_burst: int = 5

    max_bars_per_run: int = _int("BACKTEST_MAX_BARS_PER_RUN", 20000)
    max_concurrent_runs: int = _int("BACKTEST_MAX_CONCURRENT_RUNS", 1)
    queue_poll_seconds: float = _float("BACKTEST_QUEUE_POLL_SECONDS", 2.0)
    initial_equity: float = _float("BACKTEST_INITIAL_EQUITY", 10000.0)

    supported_intervals: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8088")
        object.__setattr__(self, "cors_allow_origins", [item.strip() for item in origins.split(",") if item.strip()])
        object.__setattr__(self, "supported_intervals", [item.lower() for item in _csv("INTERVALS", "1m,5m,15m,1h,4h,1d")])
        if self.auth_enabled and _is_weak_token(self.api_token):
            raise ValueError("AUTH_ENABLED=true requires a non-default API_TOKEN")


settings = Settings()
