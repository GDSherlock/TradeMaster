from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "dev-token")

try:
    from src.dataset import (  # noqa: E402
        DROP_INSUFFICIENT_FUTURE_BARS,
        DROP_INSUFFICIENT_RECENT_BARS,
        DROP_INVALID_EVENT,
        DROP_MISSING_INDICATOR_SNAPSHOT,
        DatasetBuildStats,
        SampleRow,
        explain_drop_reason,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    DROP_INSUFFICIENT_FUTURE_BARS = None
    DROP_INSUFFICIENT_RECENT_BARS = None
    DROP_INVALID_EVENT = None
    DROP_MISSING_INDICATOR_SNAPSHOT = None
    DatasetBuildStats = None
    SampleRow = None
    explain_drop_reason = None


@unittest.skipIf(DatasetBuildStats is None, "dataset dependencies are not installed in current environment")
class TestDatasetStats(unittest.TestCase):
    def test_record_failure_tracks_each_drop_reason(self) -> None:
        stats = DatasetBuildStats(total_events=4)
        stats.record_failure(DROP_INVALID_EVENT)
        stats.record_failure(DROP_MISSING_INDICATOR_SNAPSHOT)
        stats.record_failure(DROP_INSUFFICIENT_RECENT_BARS)
        stats.record_failure(DROP_INSUFFICIENT_FUTURE_BARS)

        self.assertEqual(stats.dropped_invalid_event, 1)
        self.assertEqual(stats.dropped_missing_indicator_snapshot, 1)
        self.assertEqual(stats.dropped_insufficient_recent_bars, 1)
        self.assertEqual(stats.dropped_insufficient_future_bars, 1)

    def test_record_sample_updates_positive_ratio(self) -> None:
        stats = DatasetBuildStats(total_events=2)
        now = datetime.now(tz=timezone.utc)
        positive = SampleRow(
            event_id=1,
            event_ts=now,
            symbol="BTCUSDT",
            interval="1h",
            direction="long",
            features={"rsi_current": 31.0},
            y_pass=1,
            realized_return=10.0,
            y_rsi_revert=1,
        )
        negative = SampleRow(
            event_id=2,
            event_ts=now,
            symbol="BTCUSDT",
            interval="1h",
            direction="short",
            features={"rsi_current": 69.0},
            y_pass=0,
            realized_return=-5.0,
            y_rsi_revert=0,
        )

        stats.record_sample(positive)
        stats.record_sample(negative)

        self.assertEqual(stats.built_samples, 2)
        self.assertEqual(stats.positive_labels, 1)
        self.assertEqual(stats.negative_labels, 1)
        self.assertAlmostEqual(stats.positive_ratio, 0.5)

    def test_explain_drop_reason_returns_human_message(self) -> None:
        self.assertEqual(explain_drop_reason(DROP_INVALID_EVENT), "invalid event payload")
        self.assertEqual(explain_drop_reason("unknown"), "insufficient features")


if __name__ == "__main__":
    unittest.main()
