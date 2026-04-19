from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dsl import DslValidationError, normalize_dsl


class DslValidationTests(unittest.TestCase):
    def test_normalize_valid_strategy(self) -> None:
        dsl = normalize_dsl(
            {
                "entry": {
                    "logic": "all",
                    "clauses": [
                        {"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"},
                        {
                            "type": "indicator_compare",
                            "side": "long",
                            "left": {"indicator": "ema_20", "field": "ema_20"},
                            "operator": ">",
                            "right": {"kind": "field", "indicator": "ema_50", "field": "ema_50"},
                        },
                    ],
                },
                "exit": {
                    "logic": "any",
                    "clauses": [
                        {"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERBOUGHT"},
                    ],
                },
                "sizing": {"equity_pct": 0.3, "leverage": 3, "direction_mode": "long"},
                "costs": {"fee_bps": 4, "slippage_bps": 2},
                "drawdown": {"max_total_drawdown_pct": 0.2, "trailing_drawdown_pct": 0.1, "action": "flatten_and_halt"},
                "execution": {"fill_policy": "current_bar_close"},
            }
        )

        self.assertEqual(dsl["entry"]["logic"], "all")
        self.assertEqual(dsl["entry"]["clauses"][0]["rule_key"], "RSI_OVERSOLD")
        self.assertEqual(dsl["sizing"]["direction_mode"], "long")

    def test_invalid_operator_is_rejected(self) -> None:
        with self.assertRaises(DslValidationError):
            normalize_dsl(
                {
                    "entry": {
                        "logic": "all",
                        "clauses": [
                            {
                                "type": "indicator_compare",
                                "side": "long",
                                "left": {"indicator": "ema_20", "field": "ema_20"},
                                "operator": "<>",
                                "right": {"kind": "constant", "value": 1},
                            }
                        ],
                    }
                }
            )

    def test_drawdown_requires_threshold(self) -> None:
        with self.assertRaises(DslValidationError):
            normalize_dsl(
                {
                    "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
                    "drawdown": {"action": "flatten_and_halt"},
                }
            )


if __name__ == "__main__":
    unittest.main()
