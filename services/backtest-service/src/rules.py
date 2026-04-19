from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Snapshot:
    close_current: float | None
    close_previous: float | None
    indicators_current: dict[str, dict[str, Any]]
    indicators_previous: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class RuleResult:
    rule_key: str
    direction: str
    triggered: bool


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _indicator(snapshot: Snapshot, name: str, field: str, previous: bool = False) -> float | None:
    source = snapshot.indicators_previous if previous else snapshot.indicators_current
    return _to_float((source.get(name) or {}).get(field))


def _cross_up(a_prev: float | None, a_cur: float | None, b_prev: float | None, b_cur: float | None) -> bool:
    if None in {a_prev, a_cur, b_prev, b_cur}:
        return False
    return a_prev <= b_prev and a_cur > b_cur


def _cross_down(a_prev: float | None, a_cur: float | None, b_prev: float | None, b_cur: float | None) -> bool:
    if None in {a_prev, a_cur, b_prev, b_cur}:
        return False
    return a_prev >= b_prev and a_cur < b_cur


def evaluate_signal_rule(rule_key: str, snapshot: Snapshot) -> RuleResult | None:
    key = rule_key.upper()

    if key == "RSI_OVERBOUGHT":
        cur = _indicator(snapshot, "rsi_14", "rsi_14")
        prev = _indicator(snapshot, "rsi_14", "rsi_14", previous=True)
        return RuleResult(rule_key=key, direction="short", triggered=cur is not None and prev is not None and cur >= 70.0 and prev < 70.0)

    if key == "RSI_OVERSOLD":
        cur = _indicator(snapshot, "rsi_14", "rsi_14")
        prev = _indicator(snapshot, "rsi_14", "rsi_14", previous=True)
        return RuleResult(rule_key=key, direction="long", triggered=cur is not None and prev is not None and cur <= 30.0 and prev > 30.0)

    if key in {"EMA_BULL_CROSS", "EMA_BEAR_CROSS"}:
        ema20_cur = _indicator(snapshot, "ema_20", "ema_20")
        ema20_prev = _indicator(snapshot, "ema_20", "ema_20", previous=True)
        ema50_cur = _indicator(snapshot, "ema_50", "ema_50")
        ema50_prev = _indicator(snapshot, "ema_50", "ema_50", previous=True)
        bull = key == "EMA_BULL_CROSS"
        triggered = _cross_up(ema20_prev, ema20_cur, ema50_prev, ema50_cur) if bull else _cross_down(ema20_prev, ema20_cur, ema50_prev, ema50_cur)
        return RuleResult(rule_key=key, direction="long" if bull else "short", triggered=triggered)

    if key in {"MACD_BULL_CROSS", "MACD_BEAR_CROSS"}:
        macd_cur = _indicator(snapshot, "macd_12_26_9", "macd")
        macd_prev = _indicator(snapshot, "macd_12_26_9", "macd", previous=True)
        signal_cur = _indicator(snapshot, "macd_12_26_9", "signal")
        signal_prev = _indicator(snapshot, "macd_12_26_9", "signal", previous=True)
        bull = key == "MACD_BULL_CROSS"
        triggered = _cross_up(macd_prev, macd_cur, signal_prev, signal_cur) if bull else _cross_down(macd_prev, macd_cur, signal_prev, signal_cur)
        return RuleResult(rule_key=key, direction="long" if bull else "short", triggered=triggered)

    if key in {"DONCHIAN_BREAKOUT_UP", "DONCHIAN_BREAKOUT_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        upper_cur = _indicator(snapshot, "donchian_20", "upper")
        upper_prev = _indicator(snapshot, "donchian_20", "upper", previous=True)
        lower_cur = _indicator(snapshot, "donchian_20", "lower")
        lower_prev = _indicator(snapshot, "donchian_20", "lower", previous=True)
        up = key == "DONCHIAN_BREAKOUT_UP"
        triggered = _cross_up(close_prev, close_cur, upper_prev, upper_cur) if up else _cross_down(close_prev, close_cur, lower_prev, lower_cur)
        return RuleResult(rule_key=key, direction="long" if up else "short", triggered=triggered)

    if key in {"VWAP_CROSS_UP", "VWAP_CROSS_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        vwap_cur = _indicator(snapshot, "vwap", "vwap")
        vwap_prev = _indicator(snapshot, "vwap", "vwap", previous=True)
        up = key == "VWAP_CROSS_UP"
        triggered = _cross_up(close_prev, close_cur, vwap_prev, vwap_cur) if up else _cross_down(close_prev, close_cur, vwap_prev, vwap_cur)
        return RuleResult(rule_key=key, direction="long" if up else "short", triggered=triggered)

    if key in {"ICHIMOKU_CLOUD_BREAK_UP", "ICHIMOKU_CLOUD_BREAK_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        span_a_cur = _indicator(snapshot, "ichimoku_9_26_52", "span_a")
        span_a_prev = _indicator(snapshot, "ichimoku_9_26_52", "span_a", previous=True)
        span_b_cur = _indicator(snapshot, "ichimoku_9_26_52", "span_b")
        span_b_prev = _indicator(snapshot, "ichimoku_9_26_52", "span_b", previous=True)
        cloud_cur = max(span_a_cur, span_b_cur) if span_a_cur is not None and span_b_cur is not None else None
        cloud_prev = max(span_a_prev, span_b_prev) if span_a_prev is not None and span_b_prev is not None else None
        up = key == "ICHIMOKU_CLOUD_BREAK_UP"
        triggered = _cross_up(close_prev, close_cur, cloud_prev, cloud_cur) if up else _cross_down(close_prev, close_cur, cloud_prev, cloud_cur)
        return RuleResult(rule_key=key, direction="long" if up else "short", triggered=triggered)

    return None
