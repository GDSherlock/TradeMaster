from __future__ import annotations

import unittest

try:
    from src.db import _raw_candle_limit
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    _raw_candle_limit = None


@unittest.skipIf(_raw_candle_limit is None, "database dependencies are not installed in current environment")
class TestDatabaseHelpers(unittest.TestCase):
    def test_raw_candle_limit_scales_with_interval_minutes(self) -> None:
        self.assertEqual(_raw_candle_limit("5m", 10), 55)
        self.assertEqual(_raw_candle_limit("15m", 6), 105)
        self.assertEqual(_raw_candle_limit("1h", 6), 420)
        self.assertEqual(_raw_candle_limit("4h", 2), 720)

    def test_raw_candle_limit_rejects_unsupported_intervals(self) -> None:
        with self.assertRaises(ValueError):
            _raw_candle_limit("2h", 6)


if __name__ == "__main__":
    unittest.main()
