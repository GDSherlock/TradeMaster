from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import __version__
from src.auth import enforce_http_auth, enforce_ws_auth
from src.config import settings
from src.db import get_pool
from src.response import ErrorCode, api_response, error_response
from src.routers import futures_router, health_router, indicator_router, markets_router, ml_router, signal_router

LOG = logging.getLogger(__name__)

INTERVAL_MAP = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}


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

app = FastAPI(title="TradeCat MVP API", version=__version__, docs_url="/docs", redoc_url="/redoc")

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

    if request.url.path not in {"/api/health", "/docs", "/openapi.json", "/redoc"}:
        if not limiter.allow(client_ip):
            return JSONResponse(status_code=429, content=error_response(ErrorCode.RATE_LIMITED, "rate limited"))

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "invalid parameters") if exc.errors() else "invalid parameters"
    return JSONResponse(status_code=400, content=error_response(ErrorCode.PARAM_ERROR, msg))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    LOG.exception("unhandled api error")
    return JSONResponse(status_code=500, content=error_response(ErrorCode.INTERNAL_ERROR, "internal server error"))


app.include_router(health_router, prefix="/api")
app.include_router(futures_router, prefix="/api")
app.include_router(indicator_router, prefix="/api")
app.include_router(markets_router, prefix="/api")
app.include_router(ml_router, prefix="/api")
app.include_router(signal_router, prefix="/api")


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def _fetch_latest_ohlc(symbol: str, interval: str, exchange: str) -> dict | None:
    sql = """
    WITH raw AS (
      SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS bucket,
             bucket_ts, open, high, low, close, volume, quote_volume
      FROM market_data_api.v_candles_1m_v1
      WHERE exchange = %s AND symbol = %s
      ORDER BY bucket_ts DESC
      LIMIT 500
    )
    SELECT bucket,
           (array_agg(open ORDER BY bucket_ts))[1] AS open,
           MAX(high) AS high,
           MIN(low) AS low,
           (array_agg(close ORDER BY bucket_ts DESC))[1] AS close,
           SUM(volume) AS volume,
           SUM(quote_volume) AS quote_volume
    FROM raw
    GROUP BY bucket
    ORDER BY bucket DESC
    LIMIT 1
    """
    with get_pool().connection() as conn:
        row = conn.execute(sql, (INTERVAL_MAP[interval], exchange, symbol)).fetchone()
    if not row:
        return None
    return {
        "time": int(row["bucket"].timestamp() * 1000),
        "open": str(row["open"]),
        "high": str(row["high"]),
        "low": str(row["low"]),
        "close": str(row["close"]),
        "volume": str(row["volume"]),
        "volume_usd": str(row["quote_volume"] or 0),
    }


def _signal_event_to_api_item(row: dict) -> dict:
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
        "detail": row.get("detail") or "",
        "payload": dict(row.get("payload") or {}),
    }


def _fetch_signal_events(
    exchange: str,
    limit: int = 100,
    since_id: int | None = None,
    symbol: str | None = None,
    interval: str | None = None,
    rule_key: str | None = None,
) -> list[dict]:
    sql = """
    SELECT id, exchange, symbol, interval, rule_key, signal_type, direction,
           event_ts, detected_at, price, score, cooldown_seconds, detail, payload
    FROM market_data_api.v_signal_events_v1
    WHERE exchange = %s
      AND (%s::bigint IS NULL OR id > %s)
      AND (%s::text IS NULL OR symbol = %s)
      AND (%s::text IS NULL OR interval = %s)
      AND (%s::text IS NULL OR rule_key = %s)
    ORDER BY id ASC
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(
            sql,
            (exchange, since_id, since_id, symbol, symbol, interval, interval, rule_key, rule_key, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.websocket("/ws/market")
async def ws_market(websocket: WebSocket):
    if not await enforce_ws_auth(websocket):
        return
    await websocket.accept()

    symbol = _normalize_symbol(websocket.query_params.get("symbol", "BTCUSDT"))
    interval = websocket.query_params.get("interval", "1m")
    exchange = websocket.query_params.get("exchange", settings.default_exchange)

    if interval not in INTERVAL_MAP:
        await websocket.send_json({"event": "error", "code": ErrorCode.INVALID_INTERVAL.value, "msg": "invalid interval"})
        await websocket.close(code=1003)
        return

    last_time = None
    ping_ts = time.time()

    try:
        while True:
            latest = await asyncio.to_thread(_fetch_latest_ohlc, symbol, interval, exchange)
            if latest and latest["time"] != last_time:
                last_time = latest["time"]
                await websocket.send_json({"event": "kline", "data": latest})

            if time.time() - ping_ts >= 30:
                await websocket.send_json(
                    {
                        "event": "ping",
                        "data": {"time": int(datetime.now(tz=timezone.utc).timestamp() * 1000)},
                    }
                )
                ping_ts = time.time()

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


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
                _fetch_signal_events,
                settings.default_exchange,
                200,
                since_id if since_id > 0 else None,
                symbol.upper() if symbol else None,
                interval.lower() if interval else None,
                rule_key,
            )
            for row in rows:
                item = _signal_event_to_api_item(row)
                since_id = max(since_id, item["id"])
                await websocket.send_json({"event": "signal", "data": item})

            if time.time() - ping_ts >= 30:
                await websocket.send_json(
                    {
                        "event": "ping",
                        "data": {"time": int(datetime.now(tz=timezone.utc).timestamp() * 1000)},
                    }
                )
                ping_ts = time.time()

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
