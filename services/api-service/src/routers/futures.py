from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response

from src.cache import cache
from src.config import settings
from src.db import get_pool
from src.response import ErrorCode, api_response, error_response

router = APIRouter(tags=["futures"])

INTERVAL_MAP = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith("USDT"):
        return s
    if len(s) <= 10:
        return f"{s}USDT"
    return s


@router.get("/futures/supported-coins")
def supported_coins(request: Request, response: Response):
    cache_key = f"supported_coins:{settings.default_exchange}"
    cached = cache.get(cache_key)
    if cached:
        if request.headers.get("if-none-match") == cached.etag:
            return Response(status_code=304)
        response.headers["ETag"] = cached.etag
        response.headers["Cache-Control"] = "public,max-age=30"
        return api_response(cached.data)

    sql = """
    SELECT DISTINCT symbol
    FROM market_data_api.v_candles_1m_v1
    WHERE exchange = %s
    ORDER BY symbol
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, (settings.default_exchange,)).fetchall()

    symbols = []
    for row in rows:
        symbol = row["symbol"]
        if symbol.endswith("USDT"):
            symbols.append(symbol[:-4])
        else:
            symbols.append(symbol)
    item = cache.set(cache_key, symbols, ttl_seconds=30)
    response.headers["ETag"] = item.etag
    response.headers["Cache-Control"] = "public,max-age=30"
    return api_response(symbols)


@router.get("/futures/ohlc/history")
def ohlc_history(
    response: Response,
    symbol: str = Query(...),
    exchange: str | None = Query(default=None),
    interval: str = Query(default="1h"),
    limit: int = Query(default=100, ge=1, le=1000),
    startTime: int | None = Query(default=None),
    endTime: int | None = Query(default=None),
) -> dict:
    if interval not in INTERVAL_MAP:
        return error_response(ErrorCode.INVALID_INTERVAL, f"invalid interval: {interval}")

    ex = exchange or settings.default_exchange
    sym = _normalize_symbol(symbol)
    start_dt = datetime.fromtimestamp(startTime / 1000, tz=timezone.utc) if startTime else None
    end_dt = datetime.fromtimestamp(endTime / 1000, tz=timezone.utc) if endTime else None

    sql = """
    WITH raw AS (
      SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS bucket,
             bucket_ts, open, high, low, close, volume, quote_volume
      FROM market_data_api.v_candles_1m_v1
      WHERE exchange = %s AND symbol = %s
        AND (%s::timestamptz IS NULL OR bucket_ts >= %s::timestamptz)
        AND (%s::timestamptz IS NULL OR bucket_ts <= %s::timestamptz)
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
    LIMIT %s
    """

    with get_pool().connection() as conn:
        rows = conn.execute(sql, (INTERVAL_MAP[interval], ex, sym, start_dt, start_dt, end_dt, end_dt, limit)).fetchall()

    data = [
        {
            "time": int(row["bucket"].timestamp() * 1000),
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume": str(row["volume"]),
            "volume_usd": str(row["quote_volume"] or 0),
        }
        for row in reversed(rows)
    ]
    response.headers["Cache-Control"] = "public,max-age=2"
    return api_response(data)
