from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response

from src.config import settings
from src.db import get_pool

from src.response import api_response

router = APIRouter(tags=["signal"])


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


@router.get("/signal/events")
def signal_events(
    response: Response,
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    rule_key: str | None = Query(default=None),
    since_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    sql = """
    SELECT id, exchange, symbol, interval, rule_key, signal_type, direction,
           event_ts, detected_at, price, score, cooldown_seconds, detail, payload
    FROM market_data.signal_events
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
            (
                settings.default_exchange,
                since_id,
                since_id,
                symbol.upper() if symbol else None,
                symbol.upper() if symbol else None,
                interval.lower() if interval else None,
                interval.lower() if interval else None,
                rule_key,
                rule_key,
                limit,
            ),
        ).fetchall()

    response.headers["Cache-Control"] = "public,max-age=1"
    return api_response([_event_to_api_item(dict(r)) for r in rows])


@router.get("/signal/events/latest")
def signal_events_latest(
    response: Response,
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    rule_key: str | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
) -> dict:
    sql = """
    SELECT id, exchange, symbol, interval, rule_key, signal_type, direction,
           event_ts, detected_at, price, score, cooldown_seconds, detail, payload
    FROM market_data.signal_events
    WHERE exchange = %s
      AND (%s::text IS NULL OR symbol = %s)
      AND (%s::text IS NULL OR interval = %s)
      AND (%s::text IS NULL OR rule_key = %s)
    ORDER BY id DESC
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(
            sql,
            (
                settings.default_exchange,
                symbol.upper() if symbol else None,
                symbol.upper() if symbol else None,
                interval.lower() if interval else None,
                interval.lower() if interval else None,
                rule_key,
                rule_key,
                limit,
            ),
        ).fetchall()

    response.headers["Cache-Control"] = "public,max-age=1"
    return api_response([_event_to_api_item(dict(r)) for r in rows])


@router.get("/signal/cooldown")
def signal_cooldown(limit: int = Query(default=6, ge=1, le=100)) -> dict:
    sql = """
    WITH ranked AS (
      SELECT id, exchange, symbol, interval, rule_key, signal_type, direction,
             event_ts, detected_at, price, score, cooldown_seconds, detail, payload,
             ROW_NUMBER() OVER (PARTITION BY symbol, interval ORDER BY id DESC) AS rn
      FROM market_data.signal_events
      WHERE exchange = %s
    )
    SELECT id, exchange, symbol, interval, rule_key, signal_type, direction,
           event_ts, detected_at, price, score, cooldown_seconds, detail, payload,
           GREATEST(0, EXTRACT(EPOCH FROM (detected_at + make_interval(secs => cooldown_seconds) - NOW())))::int AS cooldown_left_seconds
    FROM ranked
    WHERE rn = 1
    ORDER BY detected_at DESC
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, (settings.default_exchange, limit)).fetchall()
    return api_response([_event_to_api_item(dict(r)) for r in rows])


@router.get("/signal/rules")
def signal_rules() -> dict:
    sql = """
    SELECT rule_key, enabled, priority, cooldown_seconds, params, scope_symbols, scope_intervals, updated_at
    FROM market_data.signal_rule_configs
    ORDER BY priority DESC, rule_key ASC
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql).fetchall()

    data = [
        {
            "rule_key": r["rule_key"],
            "enabled": bool(r["enabled"]),
            "priority": int(r["priority"]),
            "cooldown_seconds": int(r["cooldown_seconds"] or 0),
            "params": dict(r["params"] or {}),
            "scope_symbols": list(r["scope_symbols"] or []),
            "scope_intervals": list(r["scope_intervals"] or []),
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]
    return api_response(data)
