from __future__ import annotations

import logging
from datetime import timedelta

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

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows]).sort_values("ts")
    df.set_index(pd.to_datetime(df["ts"], utc=True), inplace=True)
    df.drop(columns=["ts"], inplace=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _build_indicator_payloads(df: pd.DataFrame) -> dict[str, dict]:
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
        "ema_20": {"ema_20": float(ema20.iloc[-1])},
        "ema_50": {"ema_50": float(ema50.iloc[-1])},
        "ema_200": {"ema_200": float(ema200.iloc[-1])},
        "macd_12_26_9": {
            "macd": float(macd_line.iloc[-1]),
            "signal": float(macd_signal.iloc[-1]),
            "hist": float(macd_hist.iloc[-1]),
        },
        "rsi_14": {"rsi_14": float(rsi14.iloc[-1])},
        "atr_14": {"atr_14": float(atr14.iloc[-1])},
        "bbands_20": {
            "middle": float(bb_mid.iloc[-1]),
            "upper": float(bb_upper.iloc[-1]),
            "lower": float(bb_lower.iloc[-1]),
        },
        "vwap": {"vwap": float(vwap.iloc[-1])},
        "donchian_20": {
            "upper": float(donchian_upper.iloc[-1]),
            "lower": float(donchian_lower.iloc[-1]),
        },
        "ichimoku_9_26_52": {
            "tenkan": float(tenkan.iloc[-1]),
            "kijun": float(kijun.iloc[-1]),
            "span_a": float(span_a.iloc[-1]),
            "span_b": float(span_b.iloc[-1]),
        },
    }


def _safe_float_payload(payload: dict) -> dict:
    clean = {}
    for k, v in payload.items():
        if pd.isna(v):
            clean[k] = None
        else:
            clean[k] = float(v)
    return clean


def run_once(symbols: list[str], intervals: list[str]) -> int:
    rows_to_write: list[dict] = []
    for symbol in symbols:
        for interval in intervals:
            if interval not in INTERVAL_BIN:
                continue
            df = _fetch_ohlc(symbol, interval)
            if df.empty or len(df) < 60:
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
                        "payload": _safe_float_payload(payload),
                        "stale": stale,
                        "source": "indicator_engine",
                    }
                )

            state_store.set_indicator_last_ts(settings.default_exchange, symbol, interval, latest_ts)

    written = storage.upsert_indicators(rows_to_write)
    state_store.heartbeat("indicator_engine", status="running", message=f"rows={written}")
    LOG.info("indicator run complete rows=%s", written)
    return written
