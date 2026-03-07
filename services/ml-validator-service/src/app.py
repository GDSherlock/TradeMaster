from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .db import db
from .response import ErrorCode, api_response, error_response

LOG = logging.getLogger(__name__)


class InMemoryRateLimiter:
    def __init__(self, rate_per_minute: int, burst: int) -> None:
        self.rate_per_minute = max(1, rate_per_minute)
        self.burst = max(1, burst)
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            tokens, ts = self._tokens.get(key, (float(self.burst), now))
            refill = (now - ts) * (self.rate_per_minute / 60.0)
            tokens = min(float(self.burst), tokens + refill)
            if tokens < 1:
                self._tokens[key] = (tokens, now)
                return False
            tokens -= 1
            self._tokens[key] = (tokens, now)
            return True


limiter = InMemoryRateLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst)
app = FastAPI(title="TradeCat MVP ML Validator", version=__version__, docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

PUBLIC_PATHS = {"/ml/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_and_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"

    if settings.auth_enabled and request.url.path not in PUBLIC_PATHS:
        token = request.headers.get("X-API-Token", "")
        if token != settings.api_token:
            return JSONResponse(status_code=401, content=error_response(ErrorCode.UNAUTHORIZED, "unauthorized"))

    if request.url.path not in PUBLIC_PATHS:
        if not limiter.allow(client_ip):
            return JSONResponse(status_code=429, content=error_response(ErrorCode.RATE_LIMITED, "rate limited"))

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "invalid parameters") if exc.errors() else "invalid parameters"
    return JSONResponse(status_code=400, content=error_response(ErrorCode.PARAM_ERROR, msg))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    LOG.exception("unhandled ml-validator error")
    return JSONResponse(status_code=500, content=error_response(ErrorCode.INTERNAL_ERROR, "internal server error"))


@app.get("/ml/health")
def health() -> dict:
    runtime = db.fetch_runtime_state()
    return {
        "status": "healthy",
        "service": "ml-validator-service",
        "version": __version__,
        "timestamp": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "champion_version": runtime.get("champion_version"),
    }


@app.get("/ml/runtime")
def runtime() -> dict:
    state = db.fetch_runtime_state()
    latest_event_id = db.fetch_latest_signal_event_id(settings.default_exchange, settings.interval, settings.symbols)
    lag = max(0, int(latest_event_id) - int(state.get("last_processed_event_id") or 0))

    data = {
        "champion_version": state.get("champion_version"),
        "last_processed_event_id": int(state.get("last_processed_event_id") or 0),
        "last_train_run_id": state.get("last_train_run_id"),
        "last_train_at": state.get("last_train_at").isoformat() if state.get("last_train_at") else None,
        "last_train_attempt_at": state.get("last_train_attempt_at").isoformat() if state.get("last_train_attempt_at") else None,
        "last_train_status": state.get("last_train_status") or "never",
        "last_train_error": state.get("last_train_error") or None,
        "last_train_sample_count": int(state.get("last_train_sample_count") or 0),
        "last_train_positive_ratio": float(state.get("last_train_positive_ratio") or 0.0),
        "last_drift_check_at": state.get("last_drift_check_at").isoformat() if state.get("last_drift_check_at") else None,
        "last_revalidate_at": state.get("last_revalidate_at").isoformat() if state.get("last_revalidate_at") else None,
        "last_revalidate_status": state.get("last_revalidate_status") or "never",
        "last_revalidate_error": state.get("last_revalidate_error") or None,
        "last_revalidate_processed_count": int(state.get("last_revalidate_processed_count") or 0),
        "queue_lag": lag,
    }
    return api_response(data)


@app.get("/ml/training/runs")
def training_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    rows = db.fetch_training_runs(limit=limit)
    data = []
    for row in rows:
        data.append(
            {
                "id": row["id"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "train_start": row["train_start"].isoformat() if row.get("train_start") else None,
                "train_end": row["train_end"].isoformat() if row.get("train_end") else None,
                "val_start": row["val_start"].isoformat() if row.get("val_start") else None,
                "val_end": row["val_end"].isoformat() if row.get("val_end") else None,
                "test_start": row["test_start"].isoformat() if row.get("test_start") else None,
                "test_end": row["test_end"].isoformat() if row.get("test_end") else None,
                "sample_count": int(row.get("sample_count") or 0),
                "positive_ratio": float(row.get("positive_ratio") or 0.0),
                "threshold": float(row.get("threshold") or 0.0),
                "metrics": dict(row.get("metrics_json") or {}),
                "promoted": bool(row.get("promoted")),
                "notes": row.get("notes") or "",
                "run_type": row.get("run_type") or "train",
                "features_used": list(row.get("features_used") or []),
                "feature_importance": list(row.get("feature_importance") or []),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
        )
    return api_response(data)


@app.get("/ml/training/runs/{run_id}")
def training_run_detail(run_id: int) -> dict:
    row = db.fetch_training_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="training run not found")

    return api_response(
        {
            "id": row["id"],
            "model_name": row["model_name"],
            "model_version": row["model_version"],
            "train_start": row["train_start"].isoformat() if row.get("train_start") else None,
            "train_end": row["train_end"].isoformat() if row.get("train_end") else None,
            "val_start": row["val_start"].isoformat() if row.get("val_start") else None,
            "val_end": row["val_end"].isoformat() if row.get("val_end") else None,
            "test_start": row["test_start"].isoformat() if row.get("test_start") else None,
            "test_end": row["test_end"].isoformat() if row.get("test_end") else None,
            "sample_count": int(row.get("sample_count") or 0),
            "positive_ratio": float(row.get("positive_ratio") or 0.0),
            "threshold": float(row.get("threshold") or 0.0),
            "metrics": dict(row.get("metrics_json") or {}),
            "promoted": bool(row.get("promoted")),
            "notes": row.get("notes") or "",
            "run_type": row.get("run_type") or "train",
            "features_used": list(row.get("features_used") or []),
            "feature_importance": list(row.get("feature_importance") or []),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }
    )


@app.get("/ml/validation/summary")
def validation_summary(window: str = Query(default="1d")) -> dict:
    if window not in {"1d", "7d", "30d"}:
        raise HTTPException(status_code=400, detail="window must be one of 1d/7d/30d")
    return api_response(db.fetch_validation_summary(window))


@app.get("/ml/drift/latest")
def drift_latest(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    rows = db.fetch_drift_checks(limit=limit)
    data = []
    for row in rows:
        data.append(
            {
                "id": row["id"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "exchange": row["exchange"],
                "interval": row["interval"],
                "lookback_start": row["lookback_start"].isoformat() if row.get("lookback_start") else None,
                "lookback_end": row["lookback_end"].isoformat() if row.get("lookback_end") else None,
                "sample_count": int(row.get("sample_count") or 0),
                "overall_psi": float(row.get("overall_psi") or 0.0),
                "max_feature_psi": float(row.get("max_feature_psi") or 0.0),
                "threshold": float(row.get("threshold") or 0.0),
                "triggered_retrain": bool(row.get("triggered_retrain")),
                "triggered_run_id": row.get("triggered_run_id"),
                "drift_features": list(row.get("drift_features") or []),
                "notes": row.get("notes") or "",
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
        )
    return api_response(data)


@app.get("/ml/recalibration/runs")
def recalibration_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    rows = db.fetch_recalibration_runs(limit=limit)
    data = []
    for row in rows:
        data.append(
            {
                "id": row["id"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "old_threshold": float(row.get("old_threshold") or 0.0),
                "new_threshold": float(row.get("new_threshold") or 0.0),
                "lookback_start": row["lookback_start"].isoformat() if row.get("lookback_start") else None,
                "lookback_end": row["lookback_end"].isoformat() if row.get("lookback_end") else None,
                "sample_count": int(row.get("sample_count") or 0),
                "metrics": dict(row.get("metrics_json") or {}),
                "promoted": bool(row.get("promoted")),
                "notes": row.get("notes") or "",
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
        )
    return api_response(data)
