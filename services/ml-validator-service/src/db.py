from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

INTERVAL_BIN = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
}

INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

REQUIRED_INDICATORS = [
    "rsi_14",
    "ema_20",
    "ema_50",
    "ema_200",
    "macd_12_26_9",
    "atr_14",
    "bbands_20",
    "vwap",
    "donchian_20",
    "ichimoku_9_26_52",
]


def _raw_candle_limit(interval: str, bars: int) -> int:
    minutes = INTERVAL_MINUTES.get(interval)
    if minutes is None:
        raise ValueError(f"unsupported interval: {interval}")
    # Pull one extra bucket of 1m candles so aggregated windows have enough data
    # for lookback/lookahead checks on intervals larger than 15m.
    return max(1, (max(1, bars) + 1) * minutes)


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

    def _interval_bin(self, interval: str) -> str:
        if interval not in INTERVAL_BIN:
            raise ValueError(f"unsupported interval: {interval}")
        return INTERVAL_BIN[interval]

    def fetch_runtime_state(self) -> dict[str, Any]:
        sql = """
        SELECT id, champion_version, last_processed_event_id, last_train_run_id,
               last_train_at, last_train_attempt_at, last_train_status,
               last_train_error, last_train_sample_count, last_train_positive_ratio,
               last_drift_check_at, updated_at
        FROM market_data.signal_ml_runtime_state
        WHERE id = 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql).fetchone()

        if row:
            return dict(row)

        self.upsert_runtime_state(last_processed_event_id=0)
        return {
            "id": 1,
            "champion_version": None,
            "last_processed_event_id": 0,
            "last_train_run_id": None,
            "last_train_at": None,
            "last_train_attempt_at": None,
            "last_train_status": "never",
            "last_train_error": "",
            "last_train_sample_count": 0,
            "last_train_positive_ratio": 0.0,
            "last_drift_check_at": None,
            "updated_at": None,
        }

    def upsert_runtime_state(
        self,
        champion_version: str | None = None,
        last_processed_event_id: int | None = None,
        last_train_run_id: int | None = None,
        last_train_at: datetime | None = None,
        last_train_attempt_at: datetime | None = None,
        last_train_status: str | None = None,
        last_train_error: str | None = None,
        last_train_sample_count: int | None = None,
        last_train_positive_ratio: float | None = None,
        last_drift_check_at: datetime | None = None,
    ) -> None:
        sql = """
        INSERT INTO market_data.signal_ml_runtime_state (
            id, champion_version, last_processed_event_id, last_train_run_id,
            last_train_at, last_train_attempt_at, last_train_status,
            last_train_error, last_train_sample_count, last_train_positive_ratio,
            last_drift_check_at, updated_at
        )
        VALUES (1, %s, COALESCE(%s, 0), %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id)
        DO UPDATE SET
          champion_version = COALESCE(EXCLUDED.champion_version, market_data.signal_ml_runtime_state.champion_version),
          last_processed_event_id = COALESCE(EXCLUDED.last_processed_event_id, market_data.signal_ml_runtime_state.last_processed_event_id),
          last_train_run_id = COALESCE(EXCLUDED.last_train_run_id, market_data.signal_ml_runtime_state.last_train_run_id),
          last_train_at = COALESCE(EXCLUDED.last_train_at, market_data.signal_ml_runtime_state.last_train_at),
          last_train_attempt_at = COALESCE(EXCLUDED.last_train_attempt_at, market_data.signal_ml_runtime_state.last_train_attempt_at),
          last_train_status = COALESCE(EXCLUDED.last_train_status, market_data.signal_ml_runtime_state.last_train_status),
          last_train_error = COALESCE(EXCLUDED.last_train_error, market_data.signal_ml_runtime_state.last_train_error),
          last_train_sample_count = COALESCE(EXCLUDED.last_train_sample_count, market_data.signal_ml_runtime_state.last_train_sample_count),
          last_train_positive_ratio = COALESCE(EXCLUDED.last_train_positive_ratio, market_data.signal_ml_runtime_state.last_train_positive_ratio),
          last_drift_check_at = COALESCE(EXCLUDED.last_drift_check_at, market_data.signal_ml_runtime_state.last_drift_check_at),
          updated_at = NOW();
        """
        with self.pool.connection() as conn:
            conn.execute(
                sql,
                (
                    champion_version,
                    last_processed_event_id,
                    last_train_run_id,
                    last_train_at,
                    last_train_attempt_at,
                    last_train_status,
                    last_train_error,
                    last_train_sample_count,
                    last_train_positive_ratio,
                    last_drift_check_at,
                ),
            )
            conn.commit()

    def fetch_unvalidated_rsi_events(
        self,
        exchange: str,
        interval: str,
        symbols: list[str],
        since_id: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT e.id, e.exchange, e.symbol, e.interval, e.rule_key, e.direction,
               e.event_ts, e.detected_at, e.score, e.cooldown_seconds, e.payload
        FROM market_data.signal_events e
        WHERE e.exchange = %s
          AND e.interval = %s
          AND e.symbol = ANY(%s)
          AND e.rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
          AND e.id > %s
        ORDER BY e.id ASC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, interval, symbols, since_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def fetch_rsi_events_for_training(
        self,
        exchange: str,
        interval: str,
        symbols: list[str],
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT id, exchange, symbol, interval, rule_key, direction,
               event_ts, detected_at, score, cooldown_seconds, payload
        FROM market_data.signal_events
        WHERE exchange = %s
          AND interval = %s
          AND symbol = ANY(%s)
          AND rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
          AND event_ts >= %s
          AND event_ts < %s
        ORDER BY event_ts ASC, id ASC
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, interval, symbols, start_ts, end_ts)).fetchall()
        return [dict(r) for r in rows]

    def fetch_indicator_snapshot(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        event_ts: datetime,
    ) -> dict[str, Any]:
        sql = """
        WITH ranked AS (
          SELECT indicator, ts, payload,
                 ROW_NUMBER() OVER (PARTITION BY indicator ORDER BY ts DESC) AS rn
          FROM market_data.indicator_values
          WHERE exchange = %s
            AND symbol = %s
            AND interval = %s
            AND indicator = ANY(%s)
            AND ts <= %s
        )
        SELECT indicator, ts, payload, rn
        FROM ranked
        WHERE rn <= 2
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, symbol, interval, REQUIRED_INDICATORS, event_ts)).fetchall()

        current: dict[str, dict[str, Any]] = {}
        previous: dict[str, dict[str, Any]] = {}
        latest_ts: datetime | None = None

        for row in rows:
            indicator = str(row["indicator"])
            payload = dict(row.get("payload") or {})
            ts = row.get("ts")
            if isinstance(ts, datetime):
                latest_ts = max(latest_ts, ts) if latest_ts else ts
            if int(row["rn"]) == 1:
                current[indicator] = payload
            else:
                previous[indicator] = payload

        return {
            "current": current,
            "previous": previous,
            "latest_ts": latest_ts,
        }

    def fetch_recent_candles(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        event_ts: datetime,
        bars: int,
    ) -> list[dict[str, Any]]:
        if interval == "1m":
            sql = """
            SELECT bucket_ts AS ts, open, high, low, close, volume
            FROM market_data.candles_1m
            WHERE exchange = %s
              AND symbol = %s
              AND bucket_ts <= %s
            ORDER BY bucket_ts DESC
            LIMIT %s
            """
            params: tuple[Any, ...] = (exchange, symbol, event_ts, bars)
        else:
            bin_size = self._interval_bin(interval)
            raw_limit = _raw_candle_limit(interval, bars)
            sql = """
            WITH raw AS (
              SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS bucket,
                     bucket_ts, open, high, low, close, volume
              FROM market_data.candles_1m
              WHERE exchange = %s
                AND symbol = %s
                AND bucket_ts <= %s
              ORDER BY bucket_ts DESC
              LIMIT %s
            ),
            agg AS (
              SELECT bucket AS ts,
                     (array_agg(open ORDER BY bucket_ts))[1] AS open,
                     MAX(high) AS high,
                     MIN(low) AS low,
                     (array_agg(close ORDER BY bucket_ts DESC))[1] AS close,
                     SUM(volume) AS volume
              FROM raw
              GROUP BY bucket
              ORDER BY bucket DESC
              LIMIT %s
            )
            SELECT ts, open, high, low, close, volume
            FROM agg
            ORDER BY ts ASC
            """
            params = (bin_size, exchange, symbol, event_ts, raw_limit, bars)

        with self.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def fetch_future_candles(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        event_ts: datetime,
        bars: int,
    ) -> list[dict[str, Any]]:
        if interval == "1m":
            sql = """
            SELECT bucket_ts AS ts, open, high, low, close, volume
            FROM market_data.candles_1m
            WHERE exchange = %s
              AND symbol = %s
              AND bucket_ts > %s
            ORDER BY bucket_ts ASC
            LIMIT %s
            """
            params: tuple[Any, ...] = (exchange, symbol, event_ts, bars)
        else:
            bin_size = self._interval_bin(interval)
            raw_limit = _raw_candle_limit(interval, bars)
            sql = """
            WITH raw AS (
              SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS bucket,
                     bucket_ts, open, high, low, close, volume
              FROM market_data.candles_1m
              WHERE exchange = %s
                AND symbol = %s
                AND bucket_ts > %s
              ORDER BY bucket_ts ASC
              LIMIT %s
            ),
            agg AS (
              SELECT bucket AS ts,
                     (array_agg(open ORDER BY bucket_ts))[1] AS open,
                     MAX(high) AS high,
                     MIN(low) AS low,
                     (array_agg(close ORDER BY bucket_ts DESC))[1] AS close,
                     SUM(volume) AS volume
              FROM raw
              GROUP BY bucket
              ORDER BY bucket ASC
              LIMIT %s
            )
            SELECT ts, open, high, low, close, volume
            FROM agg
            ORDER BY ts ASC
            """
            params = (bin_size, exchange, symbol, event_ts, raw_limit, bars)

        with self.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def fetch_future_rsi_values(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        event_ts: datetime,
        bars: int,
    ) -> list[float]:
        sql = """
        SELECT payload
        FROM market_data.indicator_values
        WHERE exchange = %s
          AND symbol = %s
          AND interval = %s
          AND indicator = 'rsi_14'
          AND ts > %s
        ORDER BY ts ASC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (exchange, symbol, interval, event_ts, bars)).fetchall()

        values: list[float] = []
        for row in rows:
            payload = dict(row.get("payload") or {})
            try:
                values.append(float(payload.get("rsi_14")))
            except (TypeError, ValueError):
                continue
        return values

    def upsert_validation(self, payload: dict[str, Any]) -> None:
        sql = """
        INSERT INTO market_data.signal_ml_validation (
            event_id, exchange, symbol, interval, rule_key, direction, event_ts,
            model_name, model_version, probability, threshold, decision, reason,
            features, top_features, validated_at, latency_ms,
            label_horizon_bars, label_due_at, y_rsi_revert
        ) VALUES (
            %(event_id)s, %(exchange)s, %(symbol)s, %(interval)s, %(rule_key)s, %(direction)s, %(event_ts)s,
            %(model_name)s, %(model_version)s, %(probability)s, %(threshold)s, %(decision)s, %(reason)s,
            %(features)s::jsonb, %(top_features)s::jsonb, %(validated_at)s, %(latency_ms)s,
            %(label_horizon_bars)s, %(label_due_at)s, %(y_rsi_revert)s
        )
        ON CONFLICT (event_id, model_version)
        DO UPDATE SET
          probability = EXCLUDED.probability,
          threshold = EXCLUDED.threshold,
          decision = EXCLUDED.decision,
          reason = EXCLUDED.reason,
          features = EXCLUDED.features,
          top_features = EXCLUDED.top_features,
          validated_at = EXCLUDED.validated_at,
          latency_ms = EXCLUDED.latency_ms,
          label_horizon_bars = EXCLUDED.label_horizon_bars,
          label_due_at = EXCLUDED.label_due_at,
          y_rsi_revert = EXCLUDED.y_rsi_revert;
        """
        data = dict(payload)
        data["features"] = json.dumps(data.get("features") or {}, ensure_ascii=False)
        data["top_features"] = json.dumps(data.get("top_features") or [], ensure_ascii=False)

        with self.pool.connection() as conn:
            conn.execute(sql, data)
            conn.commit()

    def insert_training_run(self, payload: dict[str, Any]) -> int:
        sql = """
        INSERT INTO market_data.signal_ml_training_runs (
            model_name, model_version, train_start, train_end,
            val_start, val_end, test_start, test_end,
            sample_count, positive_ratio, threshold,
            metrics_json, promoted, notes, created_at,
            run_type, features_used, feature_importance
        ) VALUES (
            %(model_name)s, %(model_version)s, %(train_start)s, %(train_end)s,
            %(val_start)s, %(val_end)s, %(test_start)s, %(test_end)s,
            %(sample_count)s, %(positive_ratio)s, %(threshold)s,
            %(metrics_json)s::jsonb, %(promoted)s, %(notes)s, NOW(),
            %(run_type)s, %(features_used)s::jsonb, %(feature_importance)s::jsonb
        )
        RETURNING id
        """
        data = dict(payload)
        data["metrics_json"] = json.dumps(data.get("metrics_json") or {}, ensure_ascii=False)
        data["run_type"] = str(data.get("run_type") or "train")
        data["features_used"] = json.dumps(data.get("features_used") or [], ensure_ascii=False)
        data["feature_importance"] = json.dumps(data.get("feature_importance") or [], ensure_ascii=False)

        with self.pool.connection() as conn:
            row = conn.execute(sql, data).fetchone()
            conn.commit()
        return int(row["id"])

    def fetch_latest_promoted_run(self, model_name: str) -> dict[str, Any] | None:
        sql = """
        SELECT id, model_name, model_version, threshold, metrics_json, created_at
        FROM market_data.signal_ml_training_runs
        WHERE model_name = %s
          AND promoted = true
        ORDER BY created_at DESC
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (model_name,)).fetchone()
        return dict(row) if row else None

    def fetch_training_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        sql = """
        SELECT id, model_name, model_version, train_start, train_end, val_start, val_end,
               test_start, test_end, sample_count, positive_ratio, threshold,
               metrics_json, promoted, notes, created_at, run_type,
               features_used, feature_importance
        FROM market_data.signal_ml_training_runs
        ORDER BY created_at DESC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def fetch_training_run(self, run_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT id, model_name, model_version, train_start, train_end, val_start, val_end,
               test_start, test_end, sample_count, positive_ratio, threshold,
               metrics_json, promoted, notes, created_at, run_type,
               features_used, feature_importance
        FROM market_data.signal_ml_training_runs
        WHERE id = %s
        LIMIT 1
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (run_id,)).fetchone()
        return dict(row) if row else None

    def fetch_recent_model_features(
        self,
        model_version: str,
        lookback_hours: int,
        limit: int,
    ) -> tuple[list[dict[str, float]], datetime | None, datetime | None]:
        since = datetime.now(tz=timezone.utc) - timedelta(hours=max(1, lookback_hours))
        sql = """
        SELECT features, validated_at
        FROM market_data.signal_ml_validation
        WHERE model_version = %s
          AND validated_at >= %s
          AND features IS NOT NULL
        ORDER BY validated_at DESC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (model_version, since, limit)).fetchall()

        items: list[dict[str, float]] = []
        start_ts: datetime | None = None
        end_ts: datetime | None = None

        for row in rows:
            ts = row.get("validated_at")
            if isinstance(ts, datetime):
                start_ts = ts if start_ts is None else min(start_ts, ts)
                end_ts = ts if end_ts is None else max(end_ts, ts)

            raw = dict(row.get("features") or {})
            feature_map: dict[str, float] = {}
            for key, value in raw.items():
                try:
                    feature_map[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            if feature_map:
                items.append(feature_map)

        return items, start_ts, end_ts

    def insert_drift_check(self, payload: dict[str, Any]) -> int:
        sql = """
        INSERT INTO market_data.signal_ml_drift_checks (
            model_name, model_version, exchange, interval,
            lookback_start, lookback_end, sample_count,
            overall_psi, max_feature_psi, threshold,
            triggered_retrain, triggered_run_id, drift_features,
            notes, created_at
        ) VALUES (
            %(model_name)s, %(model_version)s, %(exchange)s, %(interval)s,
            %(lookback_start)s, %(lookback_end)s, %(sample_count)s,
            %(overall_psi)s, %(max_feature_psi)s, %(threshold)s,
            %(triggered_retrain)s, %(triggered_run_id)s, %(drift_features)s::jsonb,
            %(notes)s, NOW()
        )
        RETURNING id
        """
        data = dict(payload)
        data["drift_features"] = json.dumps(data.get("drift_features") or [], ensure_ascii=False)
        with self.pool.connection() as conn:
            row = conn.execute(sql, data).fetchone()
            conn.commit()
        return int(row["id"])

    def fetch_drift_checks(self, limit: int = 20) -> list[dict[str, Any]]:
        sql = """
        SELECT id, model_name, model_version, exchange, interval,
               lookback_start, lookback_end, sample_count, overall_psi,
               max_feature_psi, threshold, triggered_retrain, triggered_run_id,
               drift_features, notes, created_at
        FROM market_data.signal_ml_drift_checks
        ORDER BY created_at DESC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def insert_recalibration_run(self, payload: dict[str, Any]) -> int:
        sql = """
        INSERT INTO market_data.signal_ml_recalibration_runs (
            model_name, model_version, old_threshold, new_threshold,
            lookback_start, lookback_end, sample_count, metrics_json,
            promoted, notes, created_at
        ) VALUES (
            %(model_name)s, %(model_version)s, %(old_threshold)s, %(new_threshold)s,
            %(lookback_start)s, %(lookback_end)s, %(sample_count)s, %(metrics_json)s::jsonb,
            %(promoted)s, %(notes)s, NOW()
        )
        RETURNING id
        """
        data = dict(payload)
        data["metrics_json"] = json.dumps(data.get("metrics_json") or {}, ensure_ascii=False)
        with self.pool.connection() as conn:
            row = conn.execute(sql, data).fetchone()
            conn.commit()
        return int(row["id"])

    def fetch_recalibration_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        sql = """
        SELECT id, model_name, model_version, old_threshold, new_threshold,
               lookback_start, lookback_end, sample_count, metrics_json,
               promoted, notes, created_at
        FROM market_data.signal_ml_recalibration_runs
        ORDER BY created_at DESC
        LIMIT %s
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def fetch_validation_summary(self, window: str) -> dict[str, Any]:
        window_map = {
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        delta = window_map.get(window, timedelta(days=1))
        since = datetime.now(tz=timezone.utc) - delta

        sql = """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE decision = 'passed') AS passed,
          COUNT(*) FILTER (WHERE decision = 'review') AS review,
          COUNT(*) FILTER (WHERE decision = 'rejected') AS rejected,
          COUNT(*) FILTER (WHERE decision = 'unavailable') AS unavailable,
          AVG(probability) FILTER (WHERE probability IS NOT NULL) AS avg_probability,
          MAX(validated_at) AS latest_validated_at
        FROM market_data.signal_ml_validation
        WHERE validated_at >= %s
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (since,)).fetchone()

        data = dict(row) if row else {}
        total = int(data.get("total") or 0)
        passed = int(data.get("passed") or 0)

        return {
            "window": window,
            "since": since.isoformat(),
            "total": total,
            "passed": passed,
            "review": int(data.get("review") or 0),
            "rejected": int(data.get("rejected") or 0),
            "unavailable": int(data.get("unavailable") or 0),
            "pass_ratio": (passed / total) if total > 0 else 0.0,
            "avg_probability": float(data.get("avg_probability") or 0.0),
            "latest_validated_at": data.get("latest_validated_at").isoformat() if data.get("latest_validated_at") else None,
        }

    def fetch_latest_signal_event_id(self, exchange: str, interval: str, symbols: list[str]) -> int:
        sql = """
        SELECT COALESCE(MAX(id), 0) AS max_id
        FROM market_data.signal_events
        WHERE exchange = %s
          AND interval = %s
          AND symbol = ANY(%s)
          AND rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, interval, symbols)).fetchone()
        return int((row or {}).get("max_id") or 0)


db = Database()
