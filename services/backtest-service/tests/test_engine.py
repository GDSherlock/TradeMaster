from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engine import BarPoint, run_backtest


def bar(ts: datetime, close: float, rsi: float, ema20: float, ema50: float) -> BarPoint:
    return BarPoint(
        ts=ts,
        close=close,
        indicators={
            "rsi_14": {"rsi_14": rsi},
            "ema_20": {"ema_20": ema20},
            "ema_50": {"ema_50": ema50},
        },
    )


class EngineTests(unittest.TestCase):
    def test_signal_rule_entry_and_exit_close_on_same_bar_data(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        bars = [
            bar(start, 100, 40, 100, 100),
            bar(start + timedelta(hours=1), 101, 25, 102, 100),
            bar(start + timedelta(hours=2), 105, 75, 103, 100),
        ]
        dsl = {
            "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
            "exit": {"logic": "any", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERBOUGHT"}]},
            "sizing": {"equity_pct": 1.0, "leverage": 1.0, "direction_mode": "long"},
            "costs": {"fee_bps": 0.0, "slippage_bps": 0.0},
            "drawdown": {"max_total_drawdown_pct": 0.5, "trailing_drawdown_pct": 0.5, "action": "flatten_and_halt"},
            "execution": {"fill_policy": "current_bar_close"},
        }

        result = run_backtest(bars, dsl, start, initial_equity=10000.0)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["entry_price"], 101)
        self.assertEqual(result["trades"][0]["exit_price"], 105)
        self.assertGreater(result["summary"]["total_return_pct"], 0)

    def test_indicator_compare_supports_short_side(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        bars = [
            bar(start, 100, 50, 100, 100),
            bar(start + timedelta(hours=1), 99, 48, 99, 101),
            bar(start + timedelta(hours=2), 95, 46, 98, 102),
        ]
        dsl = {
            "entry": {
                "logic": "all",
                "clauses": [
                    {
                        "type": "indicator_compare",
                        "side": "short",
                        "left": {"indicator": "ema_20", "field": "ema_20"},
                        "operator": "<",
                        "right": {"kind": "field", "indicator": "ema_50", "field": "ema_50"},
                    }
                ],
            },
            "exit": {"logic": "any", "clauses": []},
            "sizing": {"equity_pct": 1.0, "leverage": 1.0, "direction_mode": "short"},
            "costs": {"fee_bps": 0.0, "slippage_bps": 0.0},
            "drawdown": {"max_total_drawdown_pct": 0.5, "trailing_drawdown_pct": 0.5, "action": "flatten_and_halt"},
            "execution": {"fill_policy": "current_bar_close"},
        }

        result = run_backtest(bars, dsl, start, initial_equity=10000.0)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["trades"][0]["side"], "short")
        self.assertGreater(result["trades"][0]["net_pnl"], 0)

    def test_drawdown_halt_stops_further_entries(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        bars = [
            bar(start, 100, 40, 100, 100),
            bar(start + timedelta(hours=1), 100, 25, 102, 100),
            bar(start + timedelta(hours=2), 70, 20, 103, 100),
            bar(start + timedelta(hours=3), 110, 25, 104, 100),
        ]
        dsl = {
            "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
            "exit": {"logic": "any", "clauses": []},
            "sizing": {"equity_pct": 1.0, "leverage": 4.0, "direction_mode": "long"},
            "costs": {"fee_bps": 0.0, "slippage_bps": 0.0},
            "drawdown": {"max_total_drawdown_pct": 0.2, "trailing_drawdown_pct": 0.2, "action": "flatten_and_halt"},
            "execution": {"fill_policy": "current_bar_close"},
        }

        result = run_backtest(bars, dsl, start, initial_equity=10000.0)
        self.assertTrue(result["summary"]["halted_by_drawdown"])
        self.assertEqual(result["summary"]["halt_reason"], "drawdown")
        self.assertEqual(len(result["trades"]), 1)


if __name__ == "__main__":
    unittest.main()
