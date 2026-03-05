from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from src.features import build_feature_map


class TestFeatures(unittest.TestCase):
    def test_build_feature_map_returns_finite_values(self) -> None:
        event = {
            "direction": "bullish",
            "event_ts": datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc),
            "cooldown_seconds": 900,
        }
        snapshot = {
            "current": {
                "rsi_14": {"rsi_14": 28.0},
                "ema_20": {"ema_20": 100.0},
                "ema_50": {"ema_50": 98.0},
                "ema_200": {"ema_200": 92.0},
                "macd_12_26_9": {"macd": 1.2, "signal": 1.0, "hist": 0.2},
                "atr_14": {"atr_14": 2.1},
                "bbands_20": {"upper": 105.0, "lower": 95.0, "middle": 100.0},
                "vwap": {"vwap": 99.0},
                "donchian_20": {"upper": 106.0, "lower": 94.0},
                "ichimoku_9_26_52": {"span_a": 97.0, "span_b": 96.0},
            },
            "previous": {
                "rsi_14": {"rsi_14": 25.0},
            },
        }
        candles = [
            {"close": 98.0, "volume": 1200.0},
            {"close": 99.0, "volume": 1300.0},
            {"close": 100.0, "volume": 1100.0},
            {"close": 101.0, "volume": 1400.0},
            {"close": 102.0, "volume": 1250.0},
            {"close": 101.5, "volume": 1180.0},
            {"close": 103.0, "volume": 1500.0},
        ]

        feat = build_feature_map(event, snapshot, candles)
        self.assertGreater(len(feat), 10)
        self.assertIn("rsi_current", feat)
        self.assertIn("ret_6", feat)
        for value in feat.values():
            self.assertTrue(math.isfinite(float(value)))


if __name__ == "__main__":
    unittest.main()
