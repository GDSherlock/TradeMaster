from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from src.recalibration import _build_frame
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    _build_frame = None


@dataclass
class _Sample:
    event_id: int
    event_ts: datetime
    y_pass: int
    features: dict[str, float]


@unittest.skipIf(_build_frame is None, "recalibration dependencies are not installed in current environment")
class TestRecalibration(unittest.TestCase):
    def test_build_frame_sorts_by_event_ts(self) -> None:
        samples = [
            _Sample(event_id=2, event_ts=datetime(2026, 1, 2, tzinfo=timezone.utc), y_pass=0, features={"a": 1.0}),
            _Sample(event_id=1, event_ts=datetime(2026, 1, 1, tzinfo=timezone.utc), y_pass=1, features={"a": 2.0}),
        ]

        df = _build_frame(samples)
        self.assertEqual(df.iloc[0]["event_id"], 1)
        self.assertEqual(df.iloc[1]["event_id"], 2)
        self.assertIn("a", df.columns)


if __name__ == "__main__":
    unittest.main()
