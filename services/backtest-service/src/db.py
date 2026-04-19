from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .catalog import SIGNAL_RULES
from .config import settings

INTERVAL_BIN = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}

INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def interval_seconds(interval: str) -> int:
    seconds = INTERVAL_SECONDS.get(interval)
    if seconds is None:
        raise ValueError("unsupported interval")
    return seconds


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        self.pool = ConnectionPool(
            conninfo=dsn or settings.database_url,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
        )

    def close(self) -> None:
        self.pool.close()

    def list_symbols(self, exchange: str) -> list[str]:
        sql = """
        SELECT DISTINCT symbol
        FROM market_data_api.v_candles_1m_v1
        WHERE exchange = %s
        ORDER BY symbol ASC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange,)).fetchall()
        return [str(row["symbol"]) for row in rows]

    def list_signal_rules(self) -> list[str]:
        sql = """
        SELECT rule_key
        FROM market_data.signal_rule_configs
        ORDER BY priority DESC, rule_key ASC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
        rules = [str(row["rule_key"]) for row in rows]
        return rules or SIGNAL_RULES

    def create_strategy_version(
        self,
        name: str,
        description: str,
        exchange: str,
        symbol: str,
        interval: str,
        dsl: dict[str, Any],
        strategy_id: int | None = None,
    ) -> dict[str, Any]:
        with self.pool.connection() as conn:
            if strategy_id is None:
                strategy_row = conn.execute(
                    """
                    INSERT INTO market_data.backtest_strategies (name, description, updated_at)
                    VALUES (%s, %s, NOW())
                    RETURNING id, name, description, created_at, updated_at
                    """,
                    (name, description),
                ).fetchone()
                strategy_id = int(strategy_row["id"])
            else:
                strategy_row = conn.execute(
                    """
                    UPDATE market_data.backtest_strategies
                    SET name = %s, description = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, name, description, created_at, updated_at
                    """,
                    (name, description, strategy_id),
                ).fetchone()
                if not strategy_row:
                    raise LookupError("strategy not found")

            version_row = conn.execute(
                """
                WITH next_version AS (
                  SELECT COALESCE(MAX(version_no), 0) + 1 AS version_no
                  FROM market_data.backtest_strategy_versions
                  WHERE strategy_id = %s
                )
                INSERT INTO market_data.backtest_strategy_versions (
                    strategy_id, version_no, exchange, symbol, interval, dsl_json
                )
                SELECT %s, version_no, %s, %s, %s, %s::jsonb
                FROM next_version
                RETURNING id, version_no, exchange, symbol, interval, dsl_json, created_at
                """,
                (strategy_id, strategy_id, exchange, symbol, interval, json.dumps(dsl)),
            ).fetchone()
            conn.commit()

        return {
            "strategy_id": int(strategy_row["id"]),
            "name": strategy_row["name"],
            "description": strategy_row["description"],
            "created_at": strategy_row["created_at"].isoformat() if strategy_row["created_at"] else None,
            "updated_at": strategy_row["updated_at"].isoformat() if strategy_row["updated_at"] else None,
            "version": {
                "id": int(version_row["id"]),
                "version_no": int(version_row["version_no"]),
                "exchange": version_row["exchange"],
                "symbol": version_row["symbol"],
                "interval": version_row["interval"],
                "dsl": dict(version_row["dsl_json"] or {}),
                "created_at": version_row["created_at"].isoformat() if version_row["created_at"] else None,
            },
        }

    def list_strategies(self) -> list[dict[str, Any]]:
        sql = """
        SELECT id, name, description, latest_version_id, latest_version_no, exchange, symbol, interval,
               dsl_json, latest_version_created_at, created_at, updated_at
        FROM market_data_api.v_backtest_strategies_v1
        ORDER BY updated_at DESC, id DESC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._format_strategy_row(dict(row)) for row in rows]

    def get_strategy(self, strategy_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT id, name, description, latest_version_id, latest_version_no, exchange, symbol, interval,
               dsl_json, latest_version_created_at, created_at, updated_at
        FROM market_data_api.v_backtest_strategies_v1
        WHERE id = %s
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (strategy_id,)).fetchone()
        return self._format_strategy_row(dict(row)) if row else None

    def list_strategy_versions(self, strategy_id: int) -> list[dict[str, Any]]:
        sql = """
        SELECT id, strategy_id, version_no, exchange, symbol, interval, dsl_json, created_at
        FROM market_data_api.v_backtest_strategy_versions_v1
        WHERE strategy_id = %s
        ORDER BY version_no DESC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (strategy_id,)).fetchall()
        return [self._format_version_row(dict(row)) for row in rows]

    def get_strategy_version(self, version_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT id, strategy_id, version_no, exchange, symbol, interval, dsl_json, created_at
        FROM market_data_api.v_backtest_strategy_versions_v1
        WHERE id = %s
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (version_id,)).fetchone()
        return self._format_version_row(dict(row)) if row else None

    def create_run(
        self,
        strategy_version: dict[str, Any],
        exchange: str,
        symbol: str,
        interval: str,
        start_ts: datetime,
        end_ts: datetime,
        run_params: dict[str, Any],
    ) -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO market_data.backtest_runs (
                    strategy_id, strategy_version_id, exchange, symbol, interval,
                    start_ts, end_ts, status, run_params, queued_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s::jsonb, NOW(), NOW(), NOW())
                RETURNING id, strategy_id, strategy_version_id, exchange, symbol, interval,
                          start_ts, end_ts, status, run_params, summary_json, error_code, error_message,
                          queued_at, started_at, finished_at, canceled_at, created_at, updated_at
                """,
                (
                    strategy_version["strategy_id"],
                    strategy_version["id"],
                    exchange,
                    symbol,
                    interval,
                    start_ts,
                    end_ts,
                    json.dumps(run_params),
                ),
            ).fetchone()
            conn.commit()
        return self._format_run_row(dict(row))

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        sql = """
        SELECT *
        FROM market_data_api.v_backtest_runs_v1
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [self._format_run_row(dict(row)) for row in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT *
        FROM market_data_api.v_backtest_runs_v1
        WHERE id = %s
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (run_id,)).fetchone()
        return self._format_run_row(dict(row)) if row else None

    def get_run_equity(self, run_id: int) -> list[dict[str, Any]]:
        sql = """
        SELECT run_id, point_no, ts, close_price, equity, cash_balance, peak_equity,
               total_drawdown_pct, trailing_drawdown_pct, position_side, position_notional, position_quantity
        FROM market_data_api.v_backtest_run_equity_points_v1
        WHERE run_id = %s
        ORDER BY point_no ASC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (run_id,)).fetchall()
        return [
            {
                "point_no": int(row["point_no"]),
                "ts": row["ts"].isoformat() if row["ts"] else None,
                "close_price": float(row["close_price"]),
                "equity": float(row["equity"]),
                "cash_balance": float(row["cash_balance"]),
                "peak_equity": float(row["peak_equity"]),
                "total_drawdown_pct": float(row["total_drawdown_pct"]),
                "trailing_drawdown_pct": float(row["trailing_drawdown_pct"]),
                "position_side": row["position_side"],
                "position_notional": float(row["position_notional"] or 0.0),
                "position_quantity": float(row["position_quantity"] or 0.0),
            }
            for row in rows
        ]

    def get_run_trades(self, run_id: int) -> list[dict[str, Any]]:
        sql = """
        SELECT id, run_id, trade_no, side, entry_ts, exit_ts, entry_price, exit_price,
               notional, quantity, leverage, gross_pnl, net_pnl, fees_paid, slippage_paid,
               bars_held, exit_reason, meta
        FROM market_data_api.v_backtest_run_trades_v1
        WHERE run_id = %s
        ORDER BY trade_no ASC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (run_id,)).fetchall()
        return [
            {
                "id": int(row["id"]),
                "trade_no": int(row["trade_no"]),
                "side": row["side"],
                "entry_ts": row["entry_ts"].isoformat() if row["entry_ts"] else None,
                "exit_ts": row["exit_ts"].isoformat() if row["exit_ts"] else None,
                "entry_price": float(row["entry_price"]),
                "exit_price": float(row["exit_price"]),
                "notional": float(row["notional"]),
                "quantity": float(row["quantity"]),
                "leverage": float(row["leverage"]),
                "gross_pnl": float(row["gross_pnl"]),
                "net_pnl": float(row["net_pnl"]),
                "fees_paid": float(row["fees_paid"]),
                "slippage_paid": float(row["slippage_paid"]),
                "bars_held": int(row["bars_held"]),
                "exit_reason": row["exit_reason"],
                "meta": dict(row["meta"] or {}),
            }
            for row in rows
        ]

    def cancel_run(self, run_id: int) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE market_data.backtest_runs
                SET status = 'canceled',
                    canceled_at = COALESCE(canceled_at, NOW()),
                    finished_at = COALESCE(finished_at, NOW()),
                    updated_at = NOW()
                WHERE id = %s
                  AND status IN ('queued', 'running')
                RETURNING id
                """,
                (run_id,),
            ).fetchone()
            conn.commit()
        if not row:
            return self.get_run(run_id)
        return self.get_run(run_id)

    def is_run_canceled(self, run_id: int) -> bool:
        sql = """
        SELECT status = 'canceled' AS canceled
        FROM market_data.backtest_runs
        WHERE id = %s
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (run_id,)).fetchone()
        return bool(row and row["canceled"])

    def claim_queued_run(self) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                WITH candidate AS (
                  SELECT id
                  FROM market_data.backtest_runs
                  WHERE status = 'queued'
                  ORDER BY queued_at ASC, id ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                UPDATE market_data.backtest_runs AS runs
                SET status = 'running',
                    started_at = NOW(),
                    updated_at = NOW()
                FROM candidate
                WHERE runs.id = candidate.id
                RETURNING runs.id, runs.strategy_id, runs.strategy_version_id, runs.exchange, runs.symbol, runs.interval,
                          runs.start_ts, runs.end_ts, runs.run_params
                """
            ).fetchone()
            conn.commit()
        return dict(row) if row else None

    def mark_run_failed(self, run_id: int, error_code: str, error_message: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE market_data.backtest_runs
                SET status = 'failed',
                    error_code = %s,
                    error_message = %s,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error_code, error_message, run_id),
            )
            conn.execute(
                """
                INSERT INTO market_data.backtest_run_events (run_id, event_ts, event_type, severity, message, payload)
                VALUES (%s, NOW(), 'run_failed', 'error', %s, %s::jsonb)
                """,
                (run_id, "Run failed.", json.dumps({"error_code": error_code})),
            )
            conn.commit()

    def mark_run_canceled(self, run_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE market_data.backtest_runs
                SET status = 'canceled',
                    canceled_at = COALESCE(canceled_at, NOW()),
                    finished_at = COALESCE(finished_at, NOW()),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (run_id,),
            )
            conn.execute(
                """
                INSERT INTO market_data.backtest_run_events (run_id, event_ts, event_type, severity, message, payload)
                VALUES (%s, NOW(), 'run_canceled', 'warn', 'Run canceled.', '{}'::jsonb)
                """,
                (run_id,),
            )
            conn.commit()

    def store_run_result(
        self,
        run_id: int,
        summary: dict[str, Any],
        trades: list[dict[str, Any]],
        equity_points: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE market_data.backtest_runs
                SET status = 'completed',
                    summary_json = %s::jsonb,
                    error_code = NULL,
                    error_message = NULL,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(summary), run_id),
            )
            for index, trade in enumerate(trades, start=1):
                conn.execute(
                    """
                    INSERT INTO market_data.backtest_run_trades (
                        run_id, trade_no, side, entry_ts, exit_ts, entry_price, exit_price,
                        notional, quantity, leverage, gross_pnl, net_pnl, fees_paid,
                        slippage_paid, bars_held, exit_reason, meta
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    """,
                    (
                        run_id,
                        index,
                        trade["side"],
                        trade["entry_ts"],
                        trade["exit_ts"],
                        trade["entry_price"],
                        trade["exit_price"],
                        trade["notional"],
                        trade["quantity"],
                        trade["leverage"],
                        trade["gross_pnl"],
                        trade["net_pnl"],
                        trade["fees_paid"],
                        trade["slippage_paid"],
                        trade["bars_held"],
                        trade["exit_reason"],
                        json.dumps(trade.get("meta") or {}),
                    ),
                )
            for index, point in enumerate(equity_points, start=1):
                conn.execute(
                    """
                    INSERT INTO market_data.backtest_run_equity_points (
                        run_id, point_no, ts, close_price, equity, cash_balance, peak_equity,
                        total_drawdown_pct, trailing_drawdown_pct, position_side, position_notional, position_quantity
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        index,
                        point["ts"],
                        point["close_price"],
                        point["equity"],
                        point["cash_balance"],
                        point["peak_equity"],
                        point["total_drawdown_pct"],
                        point["trailing_drawdown_pct"],
                        point["position_side"],
                        point["position_notional"],
                        point["position_quantity"],
                    ),
                )
            for event in events:
                conn.execute(
                    """
                    INSERT INTO market_data.backtest_run_events (run_id, event_ts, event_type, severity, message, payload)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        run_id,
                        event["event_ts"],
                        event["event_type"],
                        event["severity"],
                        event["message"],
                        json.dumps(event.get("payload") or {}),
                    ),
                )
            conn.execute(
                """
                INSERT INTO market_data.backtest_run_events (run_id, event_ts, event_type, severity, message, payload)
                VALUES (%s, NOW(), 'run_completed', 'info', 'Run completed.', '{}'::jsonb)
                """,
                (run_id,),
            )
            conn.commit()

    def fetch_bars_with_indicators(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        start_ts: datetime,
        end_ts: datetime,
        indicators: list[str],
    ) -> list[dict[str, Any]]:
        extra_start = start_ts - timedelta(seconds=interval_seconds(interval))
        with self.pool.connection() as conn:
            if interval == "1m":
                candle_rows = conn.execute(
                    """
                    SELECT bucket_ts AS ts, close
                    FROM market_data.candles_1m
                    WHERE exchange = %s
                      AND symbol = %s
                      AND bucket_ts >= %s
                      AND bucket_ts <= %s
                    ORDER BY bucket_ts ASC
                    """,
                    (exchange, symbol, extra_start, end_ts),
                ).fetchall()
            else:
                candle_rows = conn.execute(
                    """
                    WITH raw AS (
                      SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS ts,
                             bucket_ts,
                             close
                      FROM market_data.candles_1m
                      WHERE exchange = %s
                        AND symbol = %s
                        AND bucket_ts >= %s
                        AND bucket_ts <= %s
                      ORDER BY bucket_ts ASC
                    )
                    SELECT ts,
                           (array_agg(close ORDER BY bucket_ts DESC))[1] AS close
                    FROM raw
                    GROUP BY ts
                    ORDER BY ts ASC
                    """,
                    (INTERVAL_BIN[interval], exchange, symbol, extra_start, end_ts),
                ).fetchall()

            indicator_rows = conn.execute(
                """
                SELECT indicator, ts, payload
                FROM market_data.indicator_values
                WHERE exchange = %s
                  AND symbol = %s
                  AND interval = %s
                  AND indicator = ANY(%s)
                  AND ts >= %s
                  AND ts <= %s
                ORDER BY ts ASC, indicator ASC
                """,
                (exchange, symbol, interval, indicators, extra_start, end_ts),
            ).fetchall()

        indicator_map: dict[datetime, dict[str, Any]] = {}
        for row in indicator_rows:
            ts = row["ts"]
            bucket = indicator_map.setdefault(ts, {})
            bucket[row["indicator"]] = dict(row["payload"] or {})

        result = []
        for row in candle_rows:
            close = row["close"]
            if close is None:
                continue
            result.append(
                {
                    "ts": row["ts"],
                    "close": float(close),
                    "indicators": indicator_map.get(row["ts"], {}),
                }
            )
        return result

    def _format_strategy_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "description": row["description"] or "",
            "latest_version_id": int(row["latest_version_id"]) if row.get("latest_version_id") is not None else None,
            "latest_version_no": int(row["latest_version_no"]) if row.get("latest_version_no") is not None else None,
            "exchange": row.get("exchange"),
            "symbol": row.get("symbol"),
            "interval": row.get("interval"),
            "dsl": dict(row.get("dsl_json") or {}),
            "latest_version_created_at": row["latest_version_created_at"].isoformat() if row.get("latest_version_created_at") else None,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    def _format_version_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "strategy_id": int(row["strategy_id"]),
            "version_no": int(row["version_no"]),
            "exchange": row["exchange"],
            "symbol": row["symbol"],
            "interval": row["interval"],
            "dsl": dict(row["dsl_json"] or {}),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    def _format_run_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "strategy_id": int(row["strategy_id"]),
            "strategy_version_id": int(row["strategy_version_id"]),
            "version_no": int(row["version_no"]) if row.get("version_no") is not None else None,
            "strategy_name": row.get("strategy_name"),
            "strategy_description": row.get("strategy_description") or "",
            "exchange": row["exchange"],
            "symbol": row["symbol"],
            "interval": row["interval"],
            "start_ts": row["start_ts"].isoformat() if row.get("start_ts") else None,
            "end_ts": row["end_ts"].isoformat() if row.get("end_ts") else None,
            "status": row["status"],
            "run_params": dict(row.get("run_params") or {}),
            "summary": dict(row.get("summary_json") or {}),
            "error_code": row.get("error_code"),
            "error_message": row.get("error_message"),
            "queued_at": row["queued_at"].isoformat() if row.get("queued_at") else None,
            "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
            "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
            "canceled_at": row["canceled_at"].isoformat() if row.get("canceled_at") else None,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }


db = Database()
