from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "dev-token")

try:
    from src.db import _needs_revalidation, _raw_candle_limit, interval_duration  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    _needs_revalidation = None
    _raw_candle_limit = None
    interval_duration = None


@unittest.skipIf(_raw_candle_limit is None, "db dependencies are not installed in current environment")
class TestDbHelpers(unittest.TestCase):
    def test_raw_candle_limit_scales_with_interval(self) -> None:
        self.assertEqual(_raw_candle_limit("1m", 6), 7)
        self.assertEqual(_raw_candle_limit("5m", 6), 35)
        self.assertEqual(_raw_candle_limit("15m", 6), 105)
        self.assertEqual(_raw_candle_limit("1h", 6), 420)
        self.assertEqual(_raw_candle_limit("4h", 6), 1680)
        self.assertEqual(_raw_candle_limit("1d", 6), 10080)

    def test_raw_candle_limit_rejects_unknown_interval(self) -> None:
        with self.assertRaises(ValueError):
            _raw_candle_limit("2h", 6)

    def test_interval_duration_scales_with_interval(self) -> None:
        self.assertEqual(interval_duration("1m", 6).total_seconds(), 360)
        self.assertEqual(interval_duration("5m", 6).total_seconds(), 1800)
        self.assertEqual(interval_duration("15m", 6).total_seconds(), 5400)
        self.assertEqual(interval_duration("1h", 6).total_seconds(), 21600)
        self.assertEqual(interval_duration("4h", 6).total_seconds(), 86400)
        self.assertEqual(interval_duration("1d", 6).total_seconds(), 518400)

    def test_needs_revalidation_for_same_champion_unavailable(self) -> None:
        self.assertTrue(_needs_revalidation("champion_v1", "unavailable", "champion_v1"))

    def test_needs_revalidation_for_missing_or_stale_model(self) -> None:
        self.assertTrue(_needs_revalidation(None, None, "champion_v1"))
        self.assertTrue(_needs_revalidation("unavailable", "unavailable", "champion_v1"))
        self.assertTrue(_needs_revalidation("champion_v0", "rejected", "champion_v1"))

    def test_needs_revalidation_skips_inferred_current_champion(self) -> None:
        self.assertFalse(_needs_revalidation("champion_v1", "passed", "champion_v1"))
        self.assertFalse(_needs_revalidation("champion_v1", "review", "champion_v1"))
        self.assertFalse(_needs_revalidation("champion_v1", "rejected", "champion_v1"))


if __name__ == "__main__":
    unittest.main()
