from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleConfig:
    rule_key: str
    enabled: bool
    priority: int
    cooldown_seconds: int
    params: dict[str, Any]
    scope_symbols: list[str]
    scope_intervals: list[str]


@dataclass(frozen=True)
class Snapshot:
    close_current: float | None
    close_previous: float | None
    event_ts_ms: int | None
    indicators_current: dict[str, dict[str, Any]]
    indicators_previous: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class RuleResult:
    rule_key: str
    signal_type: str
    direction: str
    condition: bool
    triggered: bool
    score: float | None
    detail: str
    payload: dict[str, Any]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _indicator(snapshot: Snapshot, name: str, key: str, previous: bool = False) -> float | None:
    src = snapshot.indicators_previous if previous else snapshot.indicators_current
    payload = src.get(name) or {}
    return _to_float(payload.get(key))


def _cross_up(a_prev: float | None, a_cur: float | None, b_prev: float | None, b_cur: float | None) -> bool:
    if None in {a_prev, a_cur, b_prev, b_cur}:
        return False
    return a_prev <= b_prev and a_cur > b_cur


def _cross_down(a_prev: float | None, a_cur: float | None, b_prev: float | None, b_cur: float | None) -> bool:
    if None in {a_prev, a_cur, b_prev, b_cur}:
        return False
    return a_prev >= b_prev and a_cur < b_cur


def _within_scope(cfg: RuleConfig, symbol: str, interval: str) -> bool:
    if cfg.scope_symbols and symbol not in cfg.scope_symbols:
        return False
    if cfg.scope_intervals and interval not in cfg.scope_intervals:
        return False
    return True


def evaluate_rule(cfg: RuleConfig, symbol: str, interval: str, snapshot: Snapshot) -> RuleResult | None:
    if not cfg.enabled or not _within_scope(cfg, symbol, interval):
        return None

    key = cfg.rule_key
    params = cfg.params or {}

    if key == "RSI_OVERBOUGHT":
        overbought = _to_float(params.get("overbought")) or 70.0
        cur = _indicator(snapshot, "rsi_14", "rsi_14")
        prev = _indicator(snapshot, "rsi_14", "rsi_14", previous=True)
        condition = cur is not None and cur >= overbought
        prev_condition = prev is not None and prev >= overbought
        return RuleResult(
            rule_key=key,
            signal_type="RSI",
            direction="bearish",
            condition=condition,
            triggered=condition and not prev_condition,
            score=(cur - overbought) if cur is not None else None,
            detail=f"RSI14 >= {overbought}",
            payload={"rsi_current": cur, "rsi_previous": prev, "threshold": overbought},
        )

    if key == "RSI_OVERSOLD":
        oversold = _to_float(params.get("oversold")) or 30.0
        cur = _indicator(snapshot, "rsi_14", "rsi_14")
        prev = _indicator(snapshot, "rsi_14", "rsi_14", previous=True)
        condition = cur is not None and cur <= oversold
        prev_condition = prev is not None and prev <= oversold
        return RuleResult(
            rule_key=key,
            signal_type="RSI",
            direction="bullish",
            condition=condition,
            triggered=condition and not prev_condition,
            score=(oversold - cur) if cur is not None else None,
            detail=f"RSI14 <= {oversold}",
            payload={"rsi_current": cur, "rsi_previous": prev, "threshold": oversold},
        )

    if key in {"EMA_BULL_CROSS", "EMA_BEAR_CROSS"}:
        ema20_cur = _indicator(snapshot, "ema_20", "ema_20")
        ema20_prev = _indicator(snapshot, "ema_20", "ema_20", previous=True)
        ema50_cur = _indicator(snapshot, "ema_50", "ema_50")
        ema50_prev = _indicator(snapshot, "ema_50", "ema_50", previous=True)
        bull = key == "EMA_BULL_CROSS"
        condition = (ema20_cur or 0) > (ema50_cur or 0) if bull else (ema20_cur or 0) < (ema50_cur or 0)
        triggered = (
            _cross_up(ema20_prev, ema20_cur, ema50_prev, ema50_cur)
            if bull
            else _cross_down(ema20_prev, ema20_cur, ema50_prev, ema50_cur)
        )
        return RuleResult(
            rule_key=key,
            signal_type="EMA_CROSS",
            direction="bullish" if bull else "bearish",
            condition=condition,
            triggered=triggered,
            score=(ema20_cur - ema50_cur) if None not in {ema20_cur, ema50_cur} else None,
            detail="EMA20 cross EMA50",
            payload={
                "ema20_current": ema20_cur,
                "ema20_previous": ema20_prev,
                "ema50_current": ema50_cur,
                "ema50_previous": ema50_prev,
            },
        )

    if key in {"MACD_BULL_CROSS", "MACD_BEAR_CROSS"}:
        macd_cur = _indicator(snapshot, "macd_12_26_9", "macd")
        macd_prev = _indicator(snapshot, "macd_12_26_9", "macd", previous=True)
        sig_cur = _indicator(snapshot, "macd_12_26_9", "signal")
        sig_prev = _indicator(snapshot, "macd_12_26_9", "signal", previous=True)
        bull = key == "MACD_BULL_CROSS"
        condition = (macd_cur or 0) > (sig_cur or 0) if bull else (macd_cur or 0) < (sig_cur or 0)
        triggered = _cross_up(macd_prev, macd_cur, sig_prev, sig_cur) if bull else _cross_down(macd_prev, macd_cur, sig_prev, sig_cur)
        return RuleResult(
            rule_key=key,
            signal_type="MACD_CROSS",
            direction="bullish" if bull else "bearish",
            condition=condition,
            triggered=triggered,
            score=(macd_cur - sig_cur) if None not in {macd_cur, sig_cur} else None,
            detail="MACD line cross signal line",
            payload={
                "macd_current": macd_cur,
                "macd_previous": macd_prev,
                "signal_current": sig_cur,
                "signal_previous": sig_prev,
            },
        )

    if key in {"DONCHIAN_BREAKOUT_UP", "DONCHIAN_BREAKOUT_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        upper_cur = _indicator(snapshot, "donchian_20", "upper")
        upper_prev = _indicator(snapshot, "donchian_20", "upper", previous=True)
        lower_cur = _indicator(snapshot, "donchian_20", "lower")
        lower_prev = _indicator(snapshot, "donchian_20", "lower", previous=True)
        up = key == "DONCHIAN_BREAKOUT_UP"
        if up:
            condition = close_cur is not None and upper_cur is not None and close_cur > upper_cur
            triggered = _cross_up(close_prev, close_cur, upper_prev, upper_cur)
        else:
            condition = close_cur is not None and lower_cur is not None and close_cur < lower_cur
            triggered = _cross_down(close_prev, close_cur, lower_prev, lower_cur)
        return RuleResult(
            rule_key=key,
            signal_type="DONCHIAN_BREAKOUT",
            direction="bullish" if up else "bearish",
            condition=condition,
            triggered=triggered,
            score=(close_cur - upper_cur) if up and None not in {close_cur, upper_cur} else (lower_cur - close_cur) if None not in {close_cur, lower_cur} else None,
            detail="Close breaks Donchian channel",
            payload={
                "close_current": close_cur,
                "close_previous": close_prev,
                "upper_current": upper_cur,
                "upper_previous": upper_prev,
                "lower_current": lower_cur,
                "lower_previous": lower_prev,
            },
        )

    if key in {"VWAP_CROSS_UP", "VWAP_CROSS_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        vwap_cur = _indicator(snapshot, "vwap", "vwap")
        vwap_prev = _indicator(snapshot, "vwap", "vwap", previous=True)
        up = key == "VWAP_CROSS_UP"
        condition = (close_cur or 0) > (vwap_cur or 0) if up else (close_cur or 0) < (vwap_cur or 0)
        triggered = _cross_up(close_prev, close_cur, vwap_prev, vwap_cur) if up else _cross_down(close_prev, close_cur, vwap_prev, vwap_cur)
        return RuleResult(
            rule_key=key,
            signal_type="VWAP_CROSS",
            direction="bullish" if up else "bearish",
            condition=condition,
            triggered=triggered,
            score=(close_cur - vwap_cur) if None not in {close_cur, vwap_cur} else None,
            detail="Close cross VWAP",
            payload={
                "close_current": close_cur,
                "close_previous": close_prev,
                "vwap_current": vwap_cur,
                "vwap_previous": vwap_prev,
            },
        )

    if key in {"ICHIMOKU_CLOUD_BREAK_UP", "ICHIMOKU_CLOUD_BREAK_DOWN"}:
        close_cur = snapshot.close_current
        close_prev = snapshot.close_previous
        span_a_cur = _indicator(snapshot, "ichimoku_9_26_52", "span_a")
        span_a_prev = _indicator(snapshot, "ichimoku_9_26_52", "span_a", previous=True)
        span_b_cur = _indicator(snapshot, "ichimoku_9_26_52", "span_b")
        span_b_prev = _indicator(snapshot, "ichimoku_9_26_52", "span_b", previous=True)
        if None in {span_a_cur, span_b_cur}:
            cloud_cur = None
        else:
            cloud_cur = max(span_a_cur, span_b_cur)
        if None in {span_a_prev, span_b_prev}:
            cloud_prev = None
        else:
            cloud_prev = max(span_a_prev, span_b_prev)

        up = key == "ICHIMOKU_CLOUD_BREAK_UP"
        if up:
            condition = close_cur is not None and cloud_cur is not None and close_cur > cloud_cur
            triggered = _cross_up(close_prev, close_cur, cloud_prev, cloud_cur)
        else:
            condition = close_cur is not None and cloud_cur is not None and close_cur < cloud_cur
            triggered = _cross_down(close_prev, close_cur, cloud_prev, cloud_cur)

        return RuleResult(
            rule_key=key,
            signal_type="ICHIMOKU_CLOUD_BREAK",
            direction="bullish" if up else "bearish",
            condition=condition,
            triggered=triggered,
            score=(close_cur - cloud_cur) if None not in {close_cur, cloud_cur} else None,
            detail="Close break Ichimoku cloud",
            payload={
                "close_current": close_cur,
                "close_previous": close_prev,
                "span_a_current": span_a_cur,
                "span_a_previous": span_a_prev,
                "span_b_current": span_b_cur,
                "span_b_previous": span_b_prev,
            },
        )

    return None
