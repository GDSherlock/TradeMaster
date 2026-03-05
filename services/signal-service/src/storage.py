from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .config import settings
from .db import get_pool
from .rules import RuleConfig, Snapshot

INTERVAL_BIN = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}

REQUIRED_INDICATORS = [
    "rsi_14",
    "ema_20",
    "ema_50",
    "macd_12_26_9",
    "donchian_20",
    "vwap",
    "ichimoku_9_26_52",
]


class Storage:
    def __init__(self) -> None:
        self.pool = get_pool()

    def list_targets(self, exchange: str, symbols: list[str], intervals: list[str]) -> list[dict[str, Any]]:
        sql = """
        SELECT symbol, interval, MAX(ts) AS latest_ts
        FROM market_data.indicator_values
        WHERE exchange = %s
          AND symbol = ANY(%s)
          AND interval = ANY(%s)
        GROUP BY symbol, interval
        ORDER BY symbol, interval
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, symbols, intervals)).fetchall()
        return [dict(r) for r in rows]

    def fetch_rule_configs(self, include_disabled: bool = False) -> list[RuleConfig]:
        sql = """
        SELECT rule_key, enabled, priority, cooldown_seconds, params, scope_symbols, scope_intervals
        FROM market_data.signal_rule_configs
        {where_clause}
        ORDER BY priority DESC, rule_key ASC
        """.format(where_clause="" if include_disabled else "WHERE enabled = true")
        with self.pool.connection() as conn:
            rows = conn.execute(sql).fetchall()

        configs: list[RuleConfig] = []
        for row in rows:
            configs.append(
                RuleConfig(
                    rule_key=row["rule_key"],
                    enabled=bool(row["enabled"]),
                    priority=int(row["priority"]),
                    cooldown_seconds=max(0, int(row["cooldown_seconds"] or 0)),
                    params=dict(row["params"] or {}),
                    scope_symbols=[str(x).upper() for x in (row["scope_symbols"] or []) if str(x).strip()],
                    scope_intervals=[str(x).lower() for x in (row["scope_intervals"] or []) if str(x).strip()],
                )
            )
        return configs

    def fetch_snapshot(self, exchange: str, symbol: str, interval: str) -> Snapshot:
        sql = """
        WITH ranked AS (
          SELECT indicator, ts, payload,
                 ROW_NUMBER() OVER (PARTITION BY indicator ORDER BY ts DESC) AS rn
          FROM market_data.indicator_values
          WHERE exchange = %s
            AND symbol = %s
            AND interval = %s
            AND indicator = ANY(%s)
        )
        SELECT indicator, ts, payload, rn
        FROM ranked
        WHERE rn <= 2
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, symbol, interval, REQUIRED_INDICATORS)).fetchall()

        indicators_current: dict[str, dict[str, Any]] = {}
        indicators_previous: dict[str, dict[str, Any]] = {}
        event_ts_ms: int | None = None

        for row in rows:
            indicator = row["indicator"]
            payload = dict(row["payload"] or {})
            ts = row["ts"]
            ts_ms = int(ts.timestamp() * 1000) if ts else None
            if ts_ms is not None:
                event_ts_ms = max(event_ts_ms or 0, ts_ms)
            if row["rn"] == 1:
                indicators_current[indicator] = payload
            elif row["rn"] == 2:
                indicators_previous[indicator] = payload

        close_current, close_previous = self._fetch_close_window(exchange, symbol, interval)

        return Snapshot(
            close_current=close_current,
            close_previous=close_previous,
            event_ts_ms=event_ts_ms,
            indicators_current=indicators_current,
            indicators_previous=indicators_previous,
        )

    def _fetch_close_window(self, exchange: str, symbol: str, interval: str) -> tuple[float | None, float | None]:
        if interval == "1m":
            sql = """
            SELECT bucket_ts AS ts, close
            FROM market_data.candles_1m
            WHERE exchange = %s AND symbol = %s
            ORDER BY bucket_ts DESC
            LIMIT 2
            """
            params: tuple[Any, ...] = (exchange, symbol)
        else:
            if interval not in INTERVAL_BIN:
                return None, None
            sql = """
            WITH raw AS (
              SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS bucket,
                     bucket_ts,
                     close
              FROM market_data.candles_1m
              WHERE exchange = %s AND symbol = %s
              ORDER BY bucket_ts DESC
              LIMIT 10000
            ),
            agg AS (
              SELECT bucket,
                     (array_agg(close ORDER BY bucket_ts DESC))[1] AS close
              FROM raw
              GROUP BY bucket
              ORDER BY bucket DESC
              LIMIT 2
            )
            SELECT bucket AS ts, close
            FROM agg
            ORDER BY ts DESC
            """
            params = (INTERVAL_BIN[interval], exchange, symbol)

        with self.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return None, None

        close_current = float(rows[0]["close"]) if rows[0].get("close") is not None else None
        close_previous = float(rows[1]["close"]) if len(rows) > 1 and rows[1].get("close") is not None else None
        return close_current, close_previous

    def get_signal_state(self, exchange: str, symbol: str, interval: str, rule_key: str) -> dict[str, Any] | None:
        sql = """
        SELECT exchange, symbol, interval, rule_key, last_status, last_event_ts, cooldown_until, last_payload
        FROM market_data.signal_state
        WHERE exchange = %s AND symbol = %s AND interval = %s AND rule_key = %s
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, interval, rule_key)).fetchone()
        return dict(row) if row else None

    def upsert_signal_state(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        rule_key: str,
        last_status: str,
        last_event_ts: datetime | None,
        cooldown_until: datetime | None,
        last_payload: dict[str, Any],
    ) -> None:
        sql = """
        INSERT INTO market_data.signal_state (
            exchange, symbol, interval, rule_key, last_status, last_event_ts, cooldown_until, last_payload, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW()
        )
        ON CONFLICT (exchange, symbol, interval, rule_key)
        DO UPDATE SET
            last_status = EXCLUDED.last_status,
            last_event_ts = EXCLUDED.last_event_ts,
            cooldown_until = EXCLUDED.cooldown_until,
            last_payload = EXCLUDED.last_payload,
            updated_at = NOW();
        """
        with self.pool.connection() as conn:
            conn.execute(
                sql,
                (
                    exchange,
                    symbol,
                    interval,
                    rule_key,
                    last_status,
                    last_event_ts,
                    cooldown_until,
                    json.dumps(last_payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def insert_signal_event(self, row: dict[str, Any]) -> int:
        sql = """
        INSERT INTO market_data.signal_events (
            exchange, symbol, interval, rule_key, signal_type, direction,
            event_ts, detected_at, price, score, cooldown_seconds, detail, payload
        ) VALUES (
            %(exchange)s, %(symbol)s, %(interval)s, %(rule_key)s, %(signal_type)s, %(direction)s,
            %(event_ts)s, %(detected_at)s, %(price)s, %(score)s, %(cooldown_seconds)s, %(detail)s, %(payload)s::jsonb
        )
        RETURNING id
        """
        payload = dict(row)
        payload["payload"] = json.dumps(payload.get("payload", {}), ensure_ascii=False)

        with self.pool.connection() as conn:
            event_id = conn.execute(sql, payload).fetchone()["id"]
            conn.commit()
        return int(event_id)

    def fetch_events(
        self,
        exchange: str,
        limit: int = 100,
        since_id: int | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        rule_key: str | None = None,
    ) -> list[dict[str, Any]]:
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
        with self.pool.connection() as conn:
            rows = conn.execute(
                sql,
                (
                    exchange,
                    since_id,
                    since_id,
                    symbol,
                    symbol,
                    interval,
                    interval,
                    rule_key,
                    rule_key,
                    limit,
                ),
            ).fetchall()
        return [dict(r) for r in rows]

    def fetch_cooldown(self, exchange: str, limit: int = 6) -> list[dict[str, Any]]:
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
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, limit)).fetchall()
        return [dict(r) for r in rows]

    def heartbeat(self, component: str, status: str, message: str | None = None) -> None:
        sql = """
        INSERT INTO market_data.ingest_heartbeat (component, last_seen_at, status, message)
        VALUES (%s, NOW(), %s, %s)
        ON CONFLICT (component)
        DO UPDATE SET last_seen_at = NOW(), status = EXCLUDED.status, message = EXCLUDED.message;
        """
        with self.pool.connection() as conn:
            conn.execute(sql, (component, status, message))
            conn.commit()


storage = Storage()
