from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .auth import enforce_http_auth, enforce_ws_auth
from .config import settings
from .response import ErrorCode, api_response, error_response
from .storage import storage

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
app = FastAPI(title="TradeCat MVP Signal Service", version=__version__, docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def auth_and_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    try:
        enforce_http_auth(request)
    except Exception:
        return JSONResponse(status_code=401, content=error_response(ErrorCode.UNAUTHORIZED, "unauthorized"))

    if request.url.path not in {"/signal/health", "/docs", "/openapi.json", "/redoc"}:
        if not limiter.allow(client_ip):
            return JSONResponse(status_code=429, content=error_response(ErrorCode.RATE_LIMITED, "rate limited"))

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "invalid parameters") if exc.errors() else "invalid parameters"
    return JSONResponse(status_code=400, content=error_response(ErrorCode.PARAM_ERROR, msg))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    LOG.exception("unhandled signal-service error")
    return JSONResponse(status_code=500, content=error_response(ErrorCode.INTERNAL_ERROR, "internal server error"))


def _event_to_api_item(row: dict) -> dict:
    event_ts = row.get("event_ts")
    detected_at = row.get("detected_at")
    event_ms = int(event_ts.timestamp() * 1000) if isinstance(event_ts, datetime) else None
    detected_ms = int(detected_at.timestamp() * 1000) if isinstance(detected_at, datetime) else None

    return {
        "id": int(row["id"]),
        "key": f"{row['rule_key']}_{row['symbol']}_{row['interval']}",
        "exchange": row["exchange"],
        "symbol": row["symbol"],
        "interval": row["interval"],
        "rule_key": row["rule_key"],
        "type": row["signal_type"],
        "signal_type": row["signal_type"],
        "direction": row["direction"],
        "event_ts": event_ts.isoformat() if isinstance(event_ts, datetime) else None,
        "detected_at": detected_at.isoformat() if isinstance(detected_at, datetime) else None,
        "timestamp": event_ms,
        "detected_timestamp": detected_ms,
        "price": row.get("price"),
        "score": row.get("score"),
        "cooldown_seconds": int(row.get("cooldown_seconds") or 0),
        "cooldown_left_seconds": int(row.get("cooldown_left_seconds") or 0),
        "detail": row.get("detail") or "",
        "payload": dict(row.get("payload") or {}),
    }


@app.get("/signal/health")
def health() -> dict:
    sql = """
    SELECT component, status, message, last_seen_at
    FROM market_data.ingest_heartbeat
    WHERE component IN ('signal_engine', 'pipeline', 'live_ws', 'indicator_engine')
    ORDER BY last_seen_at DESC
    """
    with storage.pool.connection() as conn:
        rows = conn.execute(sql).fetchall()

    components = [dict(r) for r in rows]
    return {
        "status": "healthy",
        "service": "signal-service",
        "timestamp": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "components": components,
    }


@app.get("/signal/events")
def signal_events(
    response: Response,
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    rule_key: str | None = Query(default=None),
    since_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    rows = storage.fetch_events(
        exchange=settings.default_exchange,
        limit=limit,
        since_id=since_id,
        symbol=symbol.upper() if symbol else None,
        interval=interval.lower() if interval else None,
        rule_key=rule_key,
    )
    items = [_event_to_api_item(r) for r in rows]
    response.headers["Cache-Control"] = "public,max-age=1"
    return api_response(items)


@app.get("/signal/cooldown")
def signal_cooldown(limit: int = Query(default=6, ge=1, le=100)) -> dict:
    rows = storage.fetch_cooldown(settings.default_exchange, limit=limit)
    return api_response([_event_to_api_item(r) for r in rows])


@app.get("/signal/rules")
def signal_rules() -> dict:
    configs = storage.fetch_rule_configs(include_disabled=True)
    rows = [
        {
            "rule_key": c.rule_key,
            "enabled": c.enabled,
            "priority": c.priority,
            "cooldown_seconds": c.cooldown_seconds,
            "params": c.params,
            "scope_symbols": c.scope_symbols,
            "scope_intervals": c.scope_intervals,
        }
        for c in configs
    ]
    return api_response(rows)


@app.websocket("/ws/signal")
async def ws_signal(websocket: WebSocket):
    if not await enforce_ws_auth(websocket):
        return
    await websocket.accept()

    symbol = websocket.query_params.get("symbol")
    interval = websocket.query_params.get("interval")
    rule_key = websocket.query_params.get("rule_key")

    since_raw = websocket.query_params.get("since_id", "0")
    try:
        since_id = int(since_raw)
    except ValueError:
        since_id = 0

    ping_ts = time.time()

    try:
        while True:
            rows = await asyncio.to_thread(
                storage.fetch_events,
                settings.default_exchange,
                200,
                since_id if since_id > 0 else None,
                symbol.upper() if symbol else None,
                interval.lower() if interval else None,
                rule_key,
            )
            for row in rows:
                event = _event_to_api_item(row)
                since_id = max(since_id, event["id"])
                await websocket.send_json({"event": "signal", "data": event})

            if time.time() - ping_ts >= 30:
                await websocket.send_json({"event": "ping", "data": {"time": int(time.time() * 1000)}})
                ping_ts = time.time()

            await asyncio.sleep(max(0.2, settings.ws_poll_seconds))
    except WebSocketDisconnect:
        return
