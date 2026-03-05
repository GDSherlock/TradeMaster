from __future__ import annotations

from typing import Any


def _direction_sign(direction: str) -> int:
    normalized = direction.lower()
    if "bull" in normalized or "long" in normalized:
        return 1
    if "bear" in normalized or "short" in normalized:
        return -1
    return 1


def triple_barrier_label(
    event: dict[str, Any],
    snapshot: dict[str, Any],
    recent_candles: list[dict[str, Any]],
    future_candles: list[dict[str, Any]],
    horizon_bars: int,
    tp_atr_mult: float,
    sl_atr_mult: float,
) -> tuple[int, float]:
    if not recent_candles or not future_candles:
        return 0, 0.0

    entry = float(recent_candles[-1]["close"])
    if entry <= 0:
        return 0, 0.0

    atr_payload = (snapshot.get("current") or {}).get("atr_14") or {}
    atr14 = atr_payload.get("atr_14")
    try:
        atr14_value = float(atr14)
    except (TypeError, ValueError):
        atr14_value = 0.0

    atr_norm = (atr14_value / entry) if atr14_value > 0 else 0.0
    if atr_norm <= 0:
        atr_norm = 0.003

    tp = tp_atr_mult * atr_norm
    sl = -sl_atr_mult * atr_norm

    sign = _direction_sign(str(event.get("direction") or "bullish"))

    considered = future_candles[:horizon_bars]
    if not considered:
        return 0, 0.0

    for row in considered:
        high = float(row["high"])
        low = float(row["low"])

        signed_high = sign * ((high / entry) - 1.0)
        signed_low = sign * ((low / entry) - 1.0)

        favorable = max(signed_high, signed_low)
        adverse = min(signed_high, signed_low)

        if favorable >= tp and adverse <= sl:
            return 0, sign * ((float(row["close"]) / entry) - 1.0)
        if favorable >= tp:
            return 1, sign * ((float(row["close"]) / entry) - 1.0)
        if adverse <= sl:
            return 0, sign * ((float(row["close"]) / entry) - 1.0)

    final_close = float(considered[-1]["close"])
    realized = sign * ((final_close / entry) - 1.0)
    return (1 if realized > 0 else 0), realized


def rsi_revert_label(future_rsi_values: list[float]) -> int | None:
    if not future_rsi_values:
        return None
    for value in future_rsi_values:
        if 45 <= value <= 55:
            return 1
    return 0
