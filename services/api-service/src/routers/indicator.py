from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response

from src.cache import cache
from src.db import get_pool
from src.response import ErrorCode, api_response, error_response

router = APIRouter(tags=["indicator"])


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


@router.get("/indicator/list")
def indicator_list(request: Request, response: Response):
    cache_key = "indicator_list"
    cached = cache.get(cache_key)
    if cached:
        if request.headers.get("if-none-match") == cached.etag:
            return Response(status_code=304)
        response.headers["ETag"] = cached.etag
        response.headers["Cache-Control"] = "public,max-age=30"
        return api_response(cached.data)

    sql = """
    SELECT DISTINCT indicator
    FROM market_data.indicator_values
    ORDER BY indicator
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql).fetchall()
    data = [r["indicator"] for r in rows]
    item = cache.set(cache_key, data, ttl_seconds=30)
    response.headers["ETag"] = item.etag
    response.headers["Cache-Control"] = "public,max-age=30"
    return api_response(data)


@router.get("/indicator/data")
def indicator_data(
    table: str = Query(...),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    cursor: int | None = Query(default=None),
) -> dict:
    sym = _normalize_symbol(symbol) if symbol else None
    cursor_dt = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc) if cursor else None

    sql = """
    SELECT symbol, interval, indicator, ts, payload, stale
    FROM market_data.indicator_values
    WHERE indicator = %s
      AND (%s::text IS NULL OR symbol = %s)
      AND (%s::text IS NULL OR interval = %s)
      AND (%s::timestamptz IS NULL OR ts < %s::timestamptz)
    ORDER BY ts DESC
    LIMIT %s
    """

    with get_pool().connection() as conn:
        rows = conn.execute(sql, (table, sym, sym, interval, interval, cursor_dt, cursor_dt, limit)).fetchall()

    if not rows and limit == 1:
        # frontend fallback compatibility
        return api_response([])

    data = []
    for r in rows:
        payload = dict(r["payload"] or {})
        row = {
            "交易对": r["symbol"],
            "周期": r["interval"],
            "数据时间": r["ts"].isoformat(),
            "indicator": r["indicator"],
            "stale": bool(r["stale"]),
            "symbol": r["symbol"],
            "interval": r["interval"],
            "time": int(r["ts"].timestamp() * 1000),
        }
        row.update(payload)
        data.append(row)

    return api_response(data)
