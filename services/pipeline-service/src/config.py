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
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/market_data")
    default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance_futures_um")

    pipeline_host: str = os.getenv("PIPELINE_SERVICE_HOST", "0.0.0.0")
    pipeline_port: int = _int("PIPELINE_SERVICE_PORT", 9101)

    symbols: list[str] = None  # type: ignore[assignment]
    intervals: list[str] = None  # type: ignore[assignment]

    backfill_days: int = _int("BACKFILL_DAYS", 365)
    backfill_chunk_rows: int = _int("BACKFILL_CHUNK_ROWS", 100_000)
    backfill_db_batch_rows: int = _int("BACKFILL_DB_BATCH_ROWS", 10_000)
    backfill_start_ts: str = os.getenv("BACKFILL_START_TS", "2020-01-01T00:00:00Z")
    backfill_end_ts: str = os.getenv("BACKFILL_END_TS", "")
    backfill_live_guard_minutes: int = _int("BACKFILL_LIVE_GUARD_MINUTES", 10)
    backfill_with_indicators: bool = _bool("BACKFILL_WITH_INDICATORS", True)
    hf_dataset: str = os.getenv("HF_DATASET", "123olp/binance-futures-ohlcv-2018-2026")
    hf_candles_file: str = os.getenv("HF_CANDLES_FILE", "candles_1m.csv.gz")

    ws_url: str = os.getenv("WS_URL", "wss://fstream.binance.com/stream")
    ws_reconnect_max_seconds: int = _int("WS_RECONNECT_MAX_SECONDS", 60)
    ws_flush_seconds: float = _float("WS_FLUSH_SECONDS", 3.0)
    rest_fallback_interval_seconds: int = _int("REST_FALLBACK_INTERVAL_SECONDS", 60)

    indicator_schedule_seconds: int = _int("INDICATOR_SCHEDULE_SECONDS", 60)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbols", _csv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT"))
        object.__setattr__(self, "intervals", _csv("INTERVALS", "1m,5m,15m,1h,4h,1d"))


settings = Settings()
