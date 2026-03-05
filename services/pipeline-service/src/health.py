from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI

from .config import settings
from .storage import Storage

app = FastAPI(title="pipeline-service", version="0.1.0")


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


@app.get("/health")
def health() -> dict:
    db = Storage(settings.database_url)
    try:
        with db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT component, last_seen_at, status, message
                FROM market_data.ingest_heartbeat
                ORDER BY last_seen_at DESC
                """
            ).fetchall()
        components = [dict(r) for r in row]
    finally:
        db.close()

    return {
        "status": "healthy",
        "service": "pipeline-service",
        "timestamp": _now_ms(),
        "components": components,
    }


@app.get("/metrics")
def metrics() -> dict:
    db = Storage(settings.database_url)
    try:
        with db.pool.connection() as conn:
            candles = conn.execute("SELECT COUNT(*) AS c FROM market_data.candles_1m").fetchone()["c"]
            indicators = conn.execute("SELECT COUNT(*) AS c FROM market_data.indicator_values").fetchone()["c"]
    finally:
        db.close()

    return {
        "status": "ok",
        "candles_total": int(candles or 0),
        "indicators_total": int(indicators or 0),
        "timestamp": _now_ms(),
    }
