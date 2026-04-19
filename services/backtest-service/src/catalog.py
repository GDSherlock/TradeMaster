from __future__ import annotations

from copy import deepcopy

SIGNAL_RULES = [
    "RSI_OVERBOUGHT",
    "RSI_OVERSOLD",
    "EMA_BULL_CROSS",
    "EMA_BEAR_CROSS",
    "MACD_BULL_CROSS",
    "MACD_BEAR_CROSS",
    "DONCHIAN_BREAKOUT_UP",
    "DONCHIAN_BREAKOUT_DOWN",
    "VWAP_CROSS_UP",
    "VWAP_CROSS_DOWN",
    "ICHIMOKU_CLOUD_BREAK_UP",
    "ICHIMOKU_CLOUD_BREAK_DOWN",
]

INDICATOR_FIELDS = {
    "ema_20": ["ema_20"],
    "ema_50": ["ema_50"],
    "ema_200": ["ema_200"],
    "macd_12_26_9": ["macd", "signal", "hist"],
    "rsi_14": ["rsi_14"],
    "atr_14": ["atr_14"],
    "bbands_20": ["middle", "upper", "lower"],
    "vwap": ["vwap"],
    "donchian_20": ["upper", "lower"],
    "ichimoku_9_26_52": ["tenkan", "kijun", "span_a", "span_b"],
}

OPERATORS = [">", ">=", "<", "<=", "==", "!="]
SIDES = ["long", "short", "both"]
CLAUSE_SIDES = ["long", "short", "any"]

DEFAULT_DSL = {
    "entry": {"logic": "all", "clauses": []},
    "exit": {"logic": "any", "clauses": []},
    "sizing": {"equity_pct": 0.25, "leverage": 2.0, "direction_mode": "both"},
    "costs": {"fee_bps": 4.0, "slippage_bps": 2.0},
    "drawdown": {
        "max_total_drawdown_pct": 0.15,
        "trailing_drawdown_pct": 0.1,
        "action": "flatten_and_halt",
    },
    "execution": {"fill_policy": "current_bar_close"},
}


def build_catalog(symbols: list[str], supported_intervals: list[str], signal_rules: list[str]) -> dict:
    return {
        "symbols": symbols,
        "intervals": supported_intervals,
        "signal_rules": signal_rules,
        "indicator_fields": deepcopy(INDICATOR_FIELDS),
        "operators": OPERATORS,
        "direction_modes": SIDES,
        "clause_sides": CLAUSE_SIDES,
        "defaults": deepcopy(DEFAULT_DSL),
    }
