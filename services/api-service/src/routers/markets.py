from __future__ import annotations

from fastapi import APIRouter, Query

from src.config import settings
from src.db import get_pool
from src.response import api_response

router = APIRouter(tags=["markets"])

ORDER_MAP = {
    "abs": "ABS(change_pct) DESC",
    "desc": "change_pct DESC",
    "asc": "change_pct ASC",
}

BASE_CTE = """
WITH latest AS (
    SELECT DISTINCT ON (symbol) symbol, close, bucket_ts
    FROM market_data.candles_1m
    WHERE exchange = %s
    ORDER BY symbol, bucket_ts DESC
),
base AS (
    SELECT
        l.symbol,
        l.close AS last_close,
        p.close AS prev_close,
        l.bucket_ts AS last_ts,
        v.volume_24h,
        v.quote_volume_24h,
        CASE WHEN p.close IS NULL OR p.close = 0 THEN NULL
             ELSE (l.close - p.close) / p.close * 100 END AS change_pct
    FROM latest l
    LEFT JOIN LATERAL (
        SELECT close
        FROM market_data.candles_1m
        WHERE exchange = %s
          AND symbol = l.symbol
          AND bucket_ts <= l.bucket_ts - interval '24 hours'
        ORDER BY bucket_ts DESC
        LIMIT 1
    ) p ON true
    LEFT JOIN LATERAL (
        SELECT SUM(volume) AS volume_24h, SUM(quote_volume) AS quote_volume_24h
        FROM market_data.candles_1m
        WHERE exchange = %s
          AND symbol = l.symbol
          AND bucket_ts > l.bucket_ts - interval '24 hours'
          AND bucket_ts <= l.bucket_ts
    ) v ON true
)
"""


@router.get("/markets/momentum")
def momentum(exchange: str | None = Query(default=None)) -> dict:
    ex = exchange or settings.default_exchange
    sql = BASE_CTE + """
    SELECT
      COUNT(*) FILTER (WHERE change_pct > 0) AS up_count,
      COUNT(*) FILTER (WHERE change_pct < 0) AS down_count,
      COUNT(*) FILTER (WHERE change_pct = 0) AS flat_count,
      COUNT(*) AS total,
      MAX(last_ts) AS last_ts
    FROM base
    """
    with get_pool().connection() as conn:
        row = conn.execute(sql, (ex, ex, ex)).fetchone()

    return api_response(
        {
            "up_count": int(row["up_count"] or 0),
            "down_count": int(row["down_count"] or 0),
            "flat_count": int(row["flat_count"] or 0),
            "total": int(row["total"] or 0),
            "timestamp": int(row["last_ts"].timestamp() * 1000) if row["last_ts"] else None,
        }
    )


@router.get("/markets/top-movers")
def top_movers(
    limit: int = Query(default=20, ge=1, le=50),
    order: str = Query(default="abs"),
    exchange: str | None = Query(default=None),
) -> dict:
    ex = exchange or settings.default_exchange
    order_sql = ORDER_MAP.get(order, ORDER_MAP["abs"])
    sql = BASE_CTE + f"""
    SELECT symbol, last_close, prev_close, last_ts, volume_24h, quote_volume_24h, change_pct
    FROM base
    ORDER BY {order_sql}
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, (ex, ex, ex, limit)).fetchall()

    data = [
        {
            "symbol": r["symbol"],
            "last_close": str(r["last_close"]) if r["last_close"] is not None else None,
            "prev_close": str(r["prev_close"]) if r["prev_close"] is not None else None,
            "timestamp": int(r["last_ts"].timestamp() * 1000) if r["last_ts"] else None,
            "volume_24h": str(r["volume_24h"] or 0),
            "quote_volume_24h": str(r["quote_volume_24h"] or 0),
            "change_pct": float(r["change_pct"]) if r["change_pct"] is not None else None,
        }
        for r in rows
    ]
    return api_response(data)
