from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import settings
from .state_store import state_store
from .storage import storage

LOG = logging.getLogger(__name__)

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

MIN_INDICATOR_HISTORY_BARS = 60
INDICATOR_BACKFILL_SOURCE = "indicator_backfill"
INDICATOR_BACKFILL_DATASET = "candles_1m"
INDICATOR_BACKFILL_BATCH_POINTS = 5000
INDICATOR_BACKFILL_UPSERT_ROWS = 5000
INDICATOR_BACKFILL_WARMUP_BARS = 400


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _interval_delta(interval: str) -> timedelta:
    seconds = INTERVAL_SECONDS.get(interval)
    if seconds is None:
        raise ValueError(f"unsupported interval: {interval}")
    return timedelta(seconds=seconds)


def _series_value(series: pd.Series, pos: int) -> float | None:
    value = series.iloc[pos]
    if pd.isna(value):
        return None
    return float(value)


def _safe_float_payload(payload: dict[str, float | None]) -> dict[str, float | None]:
    clean: dict[str, float | None] = {}
    for key, value in payload.items():
        if pd.isna(value):
            clean[key] = None
        elif value is None:
            clean[key] = None
        else:
            clean[key] = float(value)
    return clean


def _normalize_dataframe(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("ts")
    df.set_index(pd.to_datetime(df["ts"], utc=True), inplace=True)
    df.drop(columns=["ts"], inplace=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _fetch_ohlc(symbol: str, interval: str, limit: int = 400) -> pd.DataFrame:
    if interval not in INTERVAL_BIN:
        raise ValueError(f"unsupported interval: {interval}")

    if interval == "1m":
        sql = """
        SELECT bucket_ts AS ts, open, high, low, close, volume, quote_volume
        FROM market_data.candles_1m
        WHERE exchange = %s AND symbol = %s
        ORDER BY bucket_ts DESC
        LIMIT %s
        """
        params = (settings.default_exchange, symbol, limit)
    else:
        sql = """
        WITH raw AS (
          SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS ts,
                 bucket_ts, open, high, low, close, volume, quote_volume
          FROM market_data.candles_1m
          WHERE exchange = %s AND symbol = %s
          ORDER BY bucket_ts DESC
          LIMIT %s
        )
        SELECT ts,
               (array_agg(open ORDER BY bucket_ts))[1] AS open,
               MAX(high) AS high,
               MIN(low) AS low,
               (array_agg(close ORDER BY bucket_ts DESC))[1] AS close,
               SUM(volume) AS volume,
               SUM(quote_volume) AS quote_volume
        FROM raw
        GROUP BY ts
        ORDER BY ts DESC
        LIMIT %s
        """
        params = (INTERVAL_BIN[interval], settings.default_exchange, symbol, limit * 10, limit)

    with storage.pool.connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _normalize_dataframe([dict(row) for row in rows])


def _fetch_ohlc_range(symbol: str, interval: str, start_ts: datetime, end_ts: datetime) -> pd.DataFrame:
    if interval not in INTERVAL_BIN:
        raise ValueError(f"unsupported interval: {interval}")

    if interval == "1m":
        sql = """
        SELECT bucket_ts AS ts, open, high, low, close, volume, quote_volume
        FROM market_data.candles_1m
        WHERE exchange = %s
          AND symbol = %s
          AND bucket_ts >= %s
          AND bucket_ts <= %s
        ORDER BY bucket_ts ASC
        """
        params = (settings.default_exchange, symbol, start_ts, end_ts)
    else:
        sql = """
        WITH raw AS (
          SELECT date_bin(%s::interval, bucket_ts, TIMESTAMPTZ '1970-01-01') AS ts,
                 bucket_ts, open, high, low, close, volume, quote_volume
          FROM market_data.candles_1m
          WHERE exchange = %s
            AND symbol = %s
            AND bucket_ts >= %s
            AND bucket_ts <= %s
          ORDER BY bucket_ts ASC
        )
        SELECT ts,
               (array_agg(open ORDER BY bucket_ts))[1] AS open,
               MAX(high) AS high,
               MIN(low) AS low,
               (array_agg(close ORDER BY bucket_ts DESC))[1] AS close,
               SUM(volume) AS volume,
               SUM(quote_volume) AS quote_volume
        FROM raw
        GROUP BY ts
        ORDER BY ts ASC
        """
        params = (INTERVAL_BIN[interval], settings.default_exchange, symbol, start_ts, end_ts)

    with storage.pool.connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _normalize_dataframe([dict(row) for row in rows])


def _compute_indicator_series(df: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    close = df["close"]

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    rsi14 = _rsi(close, 14)
    atr14 = _atr(df, 14)

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    typical = (df["high"] + df["low"] + close) / 3.0
    vwap = (typical * df["volume"]).cumsum() / df["volume"].replace(0, np.nan).cumsum()

    donchian_upper = df["high"].rolling(20).max()
    donchian_lower = df["low"].rolling(20).min()

    tenkan = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
    kijun = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
    span_a = (tenkan + kijun) / 2
    span_b = (df["high"].rolling(52).max() + df["low"].rolling(52).min()) / 2

    return {
        "ema_20": {"ema_20": ema20},
        "ema_50": {"ema_50": ema50},
        "ema_200": {"ema_200": ema200},
        "macd_12_26_9": {
            "macd": macd_line,
            "signal": macd_signal,
            "hist": macd_hist,
        },
        "rsi_14": {"rsi_14": rsi14},
        "atr_14": {"atr_14": atr14},
        "bbands_20": {
            "middle": bb_mid,
            "upper": bb_upper,
            "lower": bb_lower,
        },
        "vwap": {"vwap": vwap},
        "donchian_20": {
            "upper": donchian_upper,
            "lower": donchian_lower,
        },
        "ichimoku_9_26_52": {
            "tenkan": tenkan,
            "kijun": kijun,
            "span_a": span_a,
            "span_b": span_b,
        },
    }


def _build_indicator_payloads(df: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    series_map = _compute_indicator_series(df)
    last_pos = len(df.index) - 1
    return {
        indicator: _safe_float_payload(
            {field_name: _series_value(field_series, last_pos) for field_name, field_series in payload_map.items()}
        )
        for indicator, payload_map in series_map.items()
    }


def _iter_batches(rows: Iterable[dict], batch_size: int) -> Iterable[list[dict]]:
    batch: list[dict] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _build_historical_indicator_rows(
    symbol: str,
    interval: str,
    df: pd.DataFrame,
    target_start_ts: datetime,
    target_end_ts: datetime,
) -> tuple[list[dict], datetime | None]:
    if df.empty:
        return [], None

    series_map = _compute_indicator_series(df)
    rows: list[dict] = []
    latest_ts: datetime | None = None

    timestamps = list(df.index)
    for pos, ts_value in enumerate(timestamps):
        if pos < MIN_INDICATOR_HISTORY_BARS - 1:
            continue
        ts = ts_value.to_pydatetime() if hasattr(ts_value, "to_pydatetime") else ts_value
        if ts < target_start_ts or ts > target_end_ts:
            continue

        for indicator, payload_map in series_map.items():
            payload = _safe_float_payload(
                {field_name: _series_value(field_series, pos) for field_name, field_series in payload_map.items()}
            )
            rows.append(
                {
                    "exchange": settings.default_exchange,
                    "symbol": symbol,
                    "interval": interval,
                    "indicator": indicator,
                    "ts": ts,
                    "payload": payload,
                    "stale": False,
                    "source": "indicator_engine",
                }
            )
        latest_ts = ts

    return rows, latest_ts


def _indicator_backfill_resume_start(
    symbol: str,
    interval: str,
    start_ts: datetime,
    end_ts: datetime,
    resume: bool,
) -> tuple[datetime, datetime | None, int]:
    if not resume:
        return start_ts, None, 0

    row = state_store.get_backfill_state(INDICATOR_BACKFILL_SOURCE, symbol, interval)
    if not row:
        return start_ts, None, 0

    if row.get("dataset_revision") != INDICATOR_BACKFILL_DATASET:
        return start_ts, None, 0

    if row.get("requested_start_ts") != start_ts:
        return start_ts, None, 0

    stored_end = row.get("requested_end_ts")
    if stored_end is not None and stored_end > end_ts:
        return start_ts, None, 0

    last_ts = row.get("last_ts")
    rows_written = int(row.get("rows_written") or 0)
    if last_ts is None:
        return start_ts, None, rows_written

    resume_start = max(start_ts, last_ts + _interval_delta(interval))
    return resume_start, last_ts, rows_written


def run_once(symbols: list[str], intervals: list[str]) -> int:
    rows_to_write: list[dict] = []
    for symbol in symbols:
        for interval in intervals:
            if interval not in INTERVAL_BIN:
                continue
            df = _fetch_ohlc(symbol, interval)
            if df.empty or len(df) < MIN_INDICATOR_HISTORY_BARS:
                continue

            latest_ts = df.index[-1].to_pydatetime()
            last_processed = state_store.get_indicator_last_ts(settings.default_exchange, symbol, interval)
            if last_processed and latest_ts <= last_processed:
                continue

            stale = False
            if last_processed:
                sec = INTERVAL_SECONDS.get(interval, 60)
                stale = (latest_ts - last_processed) > timedelta(seconds=sec * 2)

            payloads = _build_indicator_payloads(df)
            for indicator, payload in payloads.items():
                rows_to_write.append(
                    {
                        "exchange": settings.default_exchange,
                        "symbol": symbol,
                        "interval": interval,
                        "indicator": indicator,
                        "ts": latest_ts,
                        "payload": payload,
                        "stale": stale,
                        "source": "indicator_engine",
                    }
                )

            state_store.set_indicator_last_ts(settings.default_exchange, symbol, interval, latest_ts)

    written = storage.upsert_indicators(rows_to_write)
    state_store.heartbeat("indicator_engine", status="running", message=f"rows={written}")
    LOG.info("indicator run complete rows=%s", written)
    return written


def run_historical_backfill(
    symbols: list[str],
    intervals: list[str],
    start_ts: datetime | None,
    end_ts: datetime,
    resume: bool = True,
) -> int:
    effective_start_ts = start_ts or datetime.fromtimestamp(0, tz=end_ts.tzinfo)
    total_rows = 0

    for symbol in symbols:
        first_candle_ts, last_candle_ts = storage.fetch_candle_bounds(settings.default_exchange, symbol)
        if first_candle_ts is None or last_candle_ts is None:
            continue

        symbol_start = max(effective_start_ts, first_candle_ts)
        symbol_end = min(end_ts, last_candle_ts)
        if symbol_start > symbol_end:
            continue

        for interval in intervals:
            if interval not in INTERVAL_BIN:
                continue

            interval_delta = _interval_delta(interval)
            resume_start, latest_written_ts, interval_rows = _indicator_backfill_resume_start(
                symbol=symbol,
                interval=interval,
                start_ts=symbol_start,
                end_ts=symbol_end,
                resume=resume,
            )
            if resume_start > symbol_end:
                state_store.set_backfill_state(
                    source=INDICATOR_BACKFILL_SOURCE,
                    symbol=symbol,
                    interval=interval,
                    last_ts=latest_written_ts,
                    status="done",
                    error_message=None,
                    scan_chunk_index=None,
                    chunk_rows=INDICATOR_BACKFILL_BATCH_POINTS,
                    requested_start_ts=symbol_start,
                    requested_end_ts=symbol_end,
                    rows_written=interval_rows,
                    dataset_revision=INDICATOR_BACKFILL_DATASET,
                )
                continue

            cursor = resume_start
            while cursor <= symbol_end:
                window_end = min(symbol_end, cursor + interval_delta * (INDICATOR_BACKFILL_BATCH_POINTS - 1))
                warmup_start = cursor - interval_delta * INDICATOR_BACKFILL_WARMUP_BARS
                df = _fetch_ohlc_range(symbol, interval, warmup_start, window_end)
                rows, window_latest_ts = _build_historical_indicator_rows(symbol, interval, df, cursor, window_end)

                if rows:
                    for batch in _iter_batches(rows, INDICATOR_BACKFILL_UPSERT_ROWS):
                        written = storage.upsert_indicators(batch)
                        total_rows += written
                        interval_rows += written
                    if window_latest_ts is not None:
                        latest_written_ts = window_latest_ts
                        current_state_ts = state_store.get_indicator_last_ts(
                            settings.default_exchange,
                            symbol,
                            interval,
                        )
                        if current_state_ts is None or latest_written_ts > current_state_ts:
                            state_store.set_indicator_last_ts(
                                settings.default_exchange,
                                symbol,
                                interval,
                                latest_written_ts,
                            )

                state_store.set_backfill_state(
                    source=INDICATOR_BACKFILL_SOURCE,
                    symbol=symbol,
                    interval=interval,
                    last_ts=latest_written_ts,
                    status="running",
                    error_message=None,
                    scan_chunk_index=None,
                    chunk_rows=INDICATOR_BACKFILL_BATCH_POINTS,
                    requested_start_ts=symbol_start,
                    requested_end_ts=symbol_end,
                    rows_written=interval_rows,
                    dataset_revision=INDICATOR_BACKFILL_DATASET,
                )
                cursor = window_end + interval_delta

            state_store.set_backfill_state(
                source=INDICATOR_BACKFILL_SOURCE,
                symbol=symbol,
                interval=interval,
                last_ts=latest_written_ts,
                status="done",
                error_message=None,
                scan_chunk_index=None,
                chunk_rows=INDICATOR_BACKFILL_BATCH_POINTS,
                requested_start_ts=symbol_start,
                requested_end_ts=symbol_end,
                rows_written=interval_rows,
                dataset_revision=INDICATOR_BACKFILL_DATASET,
            )

    state_store.heartbeat("indicator_engine", status="running", message=f"backfill_rows={total_rows}")
    LOG.info("indicator historical backfill complete rows=%s", total_rows)
    return total_rows
