from __future__ import annotations

import json
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

UPSERT_CANDLE_SQL = """
INSERT INTO market_data.candles_1m (
    exchange, symbol, bucket_ts, open, high, low, close, volume,
    quote_volume, trade_count, is_closed, source, ingested_at, updated_at
) VALUES (
    %(exchange)s, %(symbol)s, %(bucket_ts)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s,
    %(quote_volume)s, %(trade_count)s, %(is_closed)s, %(source)s, NOW(), NOW()
)
ON CONFLICT (exchange, symbol, bucket_ts) DO UPDATE SET
    open = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.open ELSE market_data.candles_1m.open END,
    high = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.high ELSE market_data.candles_1m.high END,
    low = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.low ELSE market_data.candles_1m.low END,
    close = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.close ELSE market_data.candles_1m.close END,
    volume = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.volume ELSE market_data.candles_1m.volume END,
    quote_volume = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.quote_volume ELSE market_data.candles_1m.quote_volume END,
    trade_count = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.trade_count ELSE market_data.candles_1m.trade_count END,
    source = CASE
      WHEN market_data.source_priority(EXCLUDED.source) >= market_data.source_priority(market_data.candles_1m.source)
      THEN EXCLUDED.source ELSE market_data.candles_1m.source END,
    is_closed = market_data.candles_1m.is_closed OR EXCLUDED.is_closed,
    updated_at = NOW();
"""

UPSERT_INDICATOR_SQL = """
INSERT INTO market_data.indicator_values (
    exchange, symbol, interval, indicator, ts, payload, stale, source, updated_at
) VALUES (
    %(exchange)s, %(symbol)s, %(interval)s, %(indicator)s, %(ts)s, %(payload)s::jsonb, %(stale)s, %(source)s, NOW()
)
ON CONFLICT (exchange, symbol, interval, indicator, ts) DO UPDATE
SET payload = EXCLUDED.payload,
    stale = EXCLUDED.stale,
    source = EXCLUDED.source,
    updated_at = NOW();
"""


class Storage:
    def __init__(self, dsn: str | None = None) -> None:
        self.pool = ConnectionPool(
            conninfo=dsn or settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )

    def close(self) -> None:
        self.pool.close()

    def upsert_candles(self, rows: Iterable[dict[str, Any]]) -> int:
        batch = list(rows)
        if not batch:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_CANDLE_SQL, batch)
            conn.commit()
        return len(batch)

    def upsert_indicators(self, rows: Iterable[dict[str, Any]]) -> int:
        batch = []
        for row in rows:
            normalized = dict(row)
            payload = normalized.get("payload", {})
            normalized["payload"] = json.dumps(payload, ensure_ascii=False)
            batch.append(normalized)
        if not batch:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_INDICATOR_SQL, batch)
            conn.commit()
        return len(batch)

    @contextmanager
    def advisory_lock(self, name: str):
        with self.pool.connection() as conn:
            conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (name,))
            try:
                yield
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (name,))

    def fetch_latest_candle_ts(self, exchange: str, symbol: str) -> datetime | None:
        sql = """
        SELECT MAX(bucket_ts) AS latest
        FROM market_data.candles_1m
        WHERE exchange = %s AND symbol = %s
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol)).fetchone()
        return row["latest"] if row else None

    def fetch_candle_bounds(self, exchange: str, symbol: str) -> tuple[datetime | None, datetime | None]:
        sql = """
        SELECT MIN(bucket_ts) AS earliest, MAX(bucket_ts) AS latest
        FROM market_data.candles_1m
        WHERE exchange = %s AND symbol = %s
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol)).fetchone()
        if not row:
            return None, None
        return row["earliest"], row["latest"]

    def list_symbols(self, exchange: str) -> list[str]:
        sql = """
        SELECT DISTINCT symbol
        FROM market_data.candles_1m
        WHERE exchange = %s
        ORDER BY symbol
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange,)).fetchall()
        return [r["symbol"] for r in rows]


storage = Storage()
