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


def _str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value if value else default


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
    host: str = os.getenv("ML_VALIDATOR_SERVICE_HOST", "0.0.0.0")
    port: int = _int("ML_VALIDATOR_SERVICE_PORT", 8003)

    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/market_data")
    default_exchange: str = os.getenv("DEFAULT_EXCHANGE", "binance_futures_um")

    auth_enabled: bool = _bool("AUTH_ENABLED", True)
    api_token: str = os.getenv("API_TOKEN", "")

    cors_allow_origins: list[str] = None  # type: ignore[assignment]
    rate_limit_per_minute: int = _int("ML_VALIDATOR_RATE_LIMIT_PER_MINUTE", 120)
    rate_limit_burst: int = _int("ML_VALIDATOR_RATE_LIMIT_BURST", 20)

    validate_loop_seconds: int = _int("ML_VALIDATE_LOOP_SECONDS", 30)
    validate_batch_size: int = _int("ML_VALIDATE_BATCH_SIZE", 200)

    train_loop_seconds: int = _int("ML_TRAIN_LOOP_SECONDS", 3600)
    train_schedule_hour: int = _int("ML_TRAIN_SCHEDULE_HOUR", 2)
    train_schedule_minute: int = _int("ML_TRAIN_SCHEDULE_MINUTE", 10)
    train_timezone: str = _str("ML_TRAIN_TIMEZONE", "Asia/Singapore")
    monitor_loop_seconds: int = _int("ML_MONITOR_LOOP_SECONDS", 60)

    recalibrate_schedule_weekday: int = _int("ML_RECALIBRATE_SCHEDULE_WEEKDAY", 6)
    recalibrate_schedule_hour: int = _int("ML_RECALIBRATE_SCHEDULE_HOUR", 2)
    recalibrate_schedule_minute: int = _int("ML_RECALIBRATE_SCHEDULE_MINUTE", 40)
    recalibrate_lookback_days: int = _int("ML_RECALIBRATE_LOOKBACK_DAYS", 60)

    model_name: str = _str("ML_MODEL_NAME", "rsi_lr_calibrated")
    model_registry_dir: str = _str("ML_MODEL_REGISTRY_DIR", str(SERVICE_ROOT / "models"))
    model_threshold_default: float = _float("ML_DECISION_THRESHOLD", 0.55)
    top_feature_count: int = _int("ML_TOP_FEATURES", 6)

    lookback_days: int = _int("ML_LOOKBACK_DAYS", 180)
    val_days: int = _int("ML_VAL_DAYS", 30)
    test_days: int = _int("ML_TEST_DAYS", 14)
    min_samples: int = _int("ML_MIN_SAMPLES", 200)

    interval: str = os.getenv("ML_INTERVAL", "1h")
    horizon_bars: int = _int("ML_HORIZON_BARS", 6)
    barrier_tp_atr_mult: float = _float("ML_BARRIER_TP_ATR_MULT", 1.0)
    barrier_sl_atr_mult: float = _float("ML_BARRIER_SL_ATR_MULT", 1.0)

    symbols: list[str] = None  # type: ignore[assignment]

    promote_min_precision_gain: float = _float("ML_PROMOTE_MIN_PRECISION_GAIN", 0.03)
    promote_max_brier_degrade: float = _float("ML_PROMOTE_MAX_BRIER_DEGRADE", 0.01)
    coverage_min: float = _float("ML_COVERAGE_MIN", 0.15)
    coverage_max: float = _float("ML_COVERAGE_MAX", 0.60)

    drift_check_hours: int = _int("ML_DRIFT_CHECK_HOURS", 6)
    drift_psi_threshold: float = _float("ML_DRIFT_PSI_THRESHOLD", 0.2)
    drift_lookback_hours: int = _int("ML_DRIFT_LOOKBACK_HOURS", 24)
    drift_sample_limit: int = _int("ML_DRIFT_SAMPLE_LIMIT", 2000)
    drift_min_samples: int = _int("ML_DRIFT_MIN_SAMPLES", 150)
    revalidate_on_promotion: bool = _bool("ML_REVALIDATE_ON_PROMOTION", True)
    revalidate_lookback_days: int = _int("ML_REVALIDATE_LOOKBACK_DAYS", 7)
    revalidate_batch_size: int = _int("ML_REVALIDATE_BATCH_SIZE", 1000)
    revalidate_max_batches: int = _int("ML_REVALIDATE_MAX_BATCHES", 10)

    def __post_init__(self) -> None:
        origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8088")
        object.__setattr__(self, "cors_allow_origins", [x.strip() for x in origins.split(",") if x.strip()])
        if self.auth_enabled and _is_weak_token(self.api_token):
            raise ValueError("AUTH_ENABLED=true requires a non-default API_TOKEN")
        object.__setattr__(self, "symbols", [x.upper() for x in _csv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")])


settings = Settings()
