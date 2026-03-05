from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def _payload_value(indicators: dict[str, dict[str, Any]], indicator: str, key: str) -> float | None:
    payload = indicators.get(indicator) or {}
    return _to_float(payload.get(key))


def _safe_ratio(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 0.0
    if b == 0:
        return 0.0
    return float(a / b)


def _returns(closes: list[float], bars: int) -> float:
    if len(closes) < bars + 1:
        return 0.0
    start = closes[-bars - 1]
    end = closes[-1]
    if start == 0:
        return 0.0
    return (end / start) - 1.0


def _volatility(closes: list[float], window: int = 6) -> float:
    if len(closes) < window + 1:
        return 0.0
    arr = np.array(closes[-(window + 1) :], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(np.log(np.where(arr > 0, arr, np.nan)))
    rets = rets[np.isfinite(rets)]
    if rets.size == 0:
        return 0.0
    return float(np.std(rets))


def _zscore(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    arr = np.array(values, dtype=float)
    mu = float(np.mean(arr[:-1])) if len(arr) > 1 else float(np.mean(arr))
    sigma = float(np.std(arr[:-1])) if len(arr) > 1 else float(np.std(arr))
    if sigma == 0:
        return 0.0
    return float((arr[-1] - mu) / sigma)


def build_feature_map(
    event: dict[str, Any],
    snapshot: dict[str, Any],
    recent_candles: list[dict[str, Any]],
) -> dict[str, float]:
    indicators_cur = snapshot.get("current") or {}
    indicators_prev = snapshot.get("previous") or {}

    closes = [float(row["close"]) for row in recent_candles if row.get("close") is not None]
    volumes = [float(row["volume"]) for row in recent_candles if row.get("volume") is not None]

    entry = closes[-1] if closes else None

    rsi_cur = _payload_value(indicators_cur, "rsi_14", "rsi_14")
    rsi_prev = _payload_value(indicators_prev, "rsi_14", "rsi_14")

    ema20 = _payload_value(indicators_cur, "ema_20", "ema_20")
    ema50 = _payload_value(indicators_cur, "ema_50", "ema_50")
    ema200 = _payload_value(indicators_cur, "ema_200", "ema_200")

    macd = _payload_value(indicators_cur, "macd_12_26_9", "macd")
    macd_signal = _payload_value(indicators_cur, "macd_12_26_9", "signal")
    macd_hist = _payload_value(indicators_cur, "macd_12_26_9", "hist")

    atr14 = _payload_value(indicators_cur, "atr_14", "atr_14")

    bb_upper = _payload_value(indicators_cur, "bbands_20", "upper")
    bb_lower = _payload_value(indicators_cur, "bbands_20", "lower")
    bb_middle = _payload_value(indicators_cur, "bbands_20", "middle")

    vwap = _payload_value(indicators_cur, "vwap", "vwap")

    don_upper = _payload_value(indicators_cur, "donchian_20", "upper")
    don_lower = _payload_value(indicators_cur, "donchian_20", "lower")

    span_a = _payload_value(indicators_cur, "ichimoku_9_26_52", "span_a")
    span_b = _payload_value(indicators_cur, "ichimoku_9_26_52", "span_b")

    if span_a is None or span_b is None:
        cloud_top = None
    else:
        cloud_top = max(span_a, span_b)

    direction = str(event.get("direction") or "").lower()
    direction_long = 1.0 if "bull" in direction or "long" in direction else 0.0

    event_ts = event.get("event_ts")
    if isinstance(event_ts, datetime):
        hour_of_day = float(event_ts.hour)
        day_of_week = float(event_ts.weekday())
    else:
        hour_of_day = 0.0
        day_of_week = 0.0

    den_don = (don_upper - don_lower) if don_upper is not None and don_lower is not None else None
    don_pos = (
        (entry - don_lower) / den_don if entry is not None and don_lower is not None and den_don not in {None, 0} else 0.5
    )

    den_bb = (bb_upper - bb_lower) if bb_upper is not None and bb_lower is not None else None
    bb_width = (den_bb / bb_middle) if den_bb is not None and bb_middle not in {None, 0} else 0.0

    features: dict[str, float] = {
        "rsi_current": float(rsi_cur or 0.0),
        "rsi_previous": float(rsi_prev or 0.0),
        "rsi_delta": float((rsi_cur - rsi_prev) if rsi_cur is not None and rsi_prev is not None else 0.0),
        "ema20_ema50_gap": float(((ema20 - ema50) / entry) if None not in {ema20, ema50, entry} and entry else 0.0),
        "ema50_ema200_gap": float(((ema50 - ema200) / entry) if None not in {ema50, ema200, entry} and entry else 0.0),
        "macd": float(macd or 0.0),
        "signal": float(macd_signal or 0.0),
        "hist": float(macd_hist or 0.0),
        "atr14_norm": float((atr14 / entry) if None not in {atr14, entry} and entry else 0.0),
        "ret_vol_6": float(_volatility(closes, 6)),
        "donchian_pos": float(don_pos if math.isfinite(don_pos) else 0.5),
        "bb_width": float(bb_width if math.isfinite(bb_width) else 0.0),
        "price_to_vwap": float(((entry - vwap) / vwap) if None not in {entry, vwap} and vwap else 0.0),
        "price_to_cloud_top": float(((entry - cloud_top) / entry) if None not in {entry, cloud_top} and entry else 0.0),
        "ret_1": float(_returns(closes, 1)),
        "ret_3": float(_returns(closes, 3)),
        "ret_6": float(_returns(closes, 6)),
        "volume_z_6": float(_zscore(volumes[-6:]) if len(volumes) >= 6 else 0.0),
        "direction_long": direction_long,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "cooldown_seconds": float(event.get("cooldown_seconds") or 0.0),
    }

    clean: dict[str, float] = {}
    for key, value in features.items():
        if not np.isfinite(value):
            clean[key] = 0.0
        else:
            clean[key] = float(value)
    return clean
