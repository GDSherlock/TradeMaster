from __future__ import annotations

import unittest

from src.labeling import rsi_revert_label, triple_barrier_label


class TestLabeling(unittest.TestCase):
    def test_triple_barrier_positive_for_bullish(self) -> None:
        event = {"direction": "bullish"}
        snapshot = {"current": {"atr_14": {"atr_14": 2.0}}}
        recent = [{"close": 100.0}]
        future = [
            {"high": 101.2, "low": 99.2, "close": 100.8},
            {"high": 102.0, "low": 100.0, "close": 101.5},
        ]

        y, realized = triple_barrier_label(
            event=event,
            snapshot=snapshot,
            recent_candles=recent,
            future_candles=future,
            horizon_bars=2,
            tp_atr_mult=1.0,
            sl_atr_mult=1.0,
        )
        self.assertEqual(y, 1)
        self.assertGreater(realized, 0)

    def test_rsi_revert_label(self) -> None:
        self.assertEqual(rsi_revert_label([30.0, 44.9, 45.0]), 1)
        self.assertEqual(rsi_revert_label([65.0, 62.0]), 0)
        self.assertIsNone(rsi_revert_label([]))


if __name__ == "__main__":
    unittest.main()
