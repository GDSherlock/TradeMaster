from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "dev-token")

from src.monitor import MonitorScheduler  # noqa: E402


class _FakeDb:
    def __init__(self) -> None:
        self.runtime_state: dict[str, object] = {}

    def fetch_runtime_state(self) -> dict[str, object]:
        return dict(self.runtime_state)

    def fetch_recalibration_runs(self, limit: int = 1) -> list[dict[str, object]]:
        return []


class TestMonitorScheduler(unittest.TestCase):
    def test_daily_train_failure_only_attempts_once_per_day(self) -> None:
        db = _FakeDb()
        scheduler = MonitorScheduler(db)
        now = datetime(2026, 3, 9, 2, 15, tzinfo=ZoneInfo("Asia/Singapore"))

        with patch("src.monitor.run_train_once", side_effect=RuntimeError("insufficient samples")) as train_once:
            scheduler._run_daily_train_if_due(now)
            scheduler._run_daily_train_if_due(now.replace(minute=45))

        self.assertEqual(train_once.call_count, 1)
        self.assertEqual(scheduler._last_train_day, "2026-03-09")

    def test_weekly_recalibration_failure_only_attempts_once_per_week(self) -> None:
        db = _FakeDb()
        scheduler = MonitorScheduler(db)
        now = datetime(2026, 3, 8, 2, 45, tzinfo=ZoneInfo("Asia/Singapore"))

        with patch("src.monitor.run_recalibration_once", side_effect=RuntimeError("recalibration failed")) as recal_once:
            scheduler._run_weekly_recalibration_if_due(now)
            scheduler._run_weekly_recalibration_if_due(now.replace(hour=3))

        self.assertEqual(recal_once.call_count, 1)
        self.assertEqual(scheduler._last_recal_week, now.strftime("%G-%V"))


if __name__ == "__main__":
    unittest.main()
