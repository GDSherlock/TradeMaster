from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import Database
from .drift import run_drift_check_once
from .recalibration import run_recalibration_once
from .trainer import run_train_once

LOG = logging.getLogger(__name__)


class MonitorScheduler:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._last_train_day: str | None = None
        self._last_recal_week: str | None = None

    def _local_now(self) -> datetime:
        try:
            tz = ZoneInfo(settings.train_timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        return datetime.now(tz=tz)

    def _run_daily_train_if_due(self, now: datetime) -> None:
        day_key = now.strftime("%Y-%m-%d")
        runtime = self.db.fetch_runtime_state()
        last_train_at = runtime.get("last_train_at")
        if isinstance(last_train_at, datetime):
            if last_train_at.astimezone(now.tzinfo).strftime("%Y-%m-%d") == day_key:
                self._last_train_day = day_key

        should_run = (
            now.hour == settings.train_schedule_hour
            and now.minute >= settings.train_schedule_minute
            and day_key != self._last_train_day
        )
        if not should_run:
            return

        # Automated schedules should attempt once per day; operators can rerun manually if needed.
        self._last_train_day = day_key
        try:
            result = run_train_once(self.db)
            LOG.info(
                "daily train done run_id=%s version=%s promoted=%s threshold=%.4f",
                result.run_id,
                result.model_version,
                result.promoted,
                result.threshold,
            )
        except Exception:
            LOG.exception("daily train failed")

    def _run_weekly_recalibration_if_due(self, now: datetime) -> None:
        year_week = now.strftime("%G-%V")
        if self._last_recal_week is None:
            latest = self.db.fetch_recalibration_runs(limit=1)
            if latest and latest[0].get("created_at"):
                created_at = latest[0]["created_at"]
                if isinstance(created_at, datetime):
                    self._last_recal_week = created_at.astimezone(now.tzinfo).strftime("%G-%V")

        should_run = (
            now.weekday() == settings.recalibrate_schedule_weekday
            and now.hour == settings.recalibrate_schedule_hour
            and now.minute >= settings.recalibrate_schedule_minute
            and year_week != self._last_recal_week
        )
        if not should_run:
            return

        # Weekly recalibration also runs at most once per scheduled window.
        self._last_recal_week = year_week
        try:
            result = run_recalibration_once(self.db)
            LOG.info(
                "weekly recalibration done id=%s version=%s promoted=%s old=%.4f new=%.4f",
                result.recalibration_id,
                result.champion_version,
                result.promoted,
                result.old_threshold,
                result.new_threshold,
            )
        except Exception:
            LOG.exception("weekly recalibration failed")

    def _run_drift_check_if_due(self) -> None:
        runtime = self.db.fetch_runtime_state()
        last_check = runtime.get("last_drift_check_at")
        now_utc = datetime.now(tz=timezone.utc)

        if isinstance(last_check, datetime):
            due = now_utc - last_check >= timedelta(hours=max(1, settings.drift_check_hours))
        else:
            due = True

        if not due:
            return

        try:
            result = run_drift_check_once(self.db, auto_retrain=True)
            LOG.info(
                "drift check done check_id=%s version=%s sample_count=%s max_psi=%.4f triggered=%s",
                result.check_id,
                result.champion_version,
                result.sample_count,
                result.max_feature_psi,
                result.triggered_retrain,
            )
        except Exception:
            LOG.exception("drift check failed")

    def run_once(self) -> None:
        now = self._local_now()
        self._run_daily_train_if_due(now)
        self._run_weekly_recalibration_if_due(now)
        self._run_drift_check_if_due()

    def run_loop(self) -> None:
        LOG.info(
            "ml monitor loop started train=%02d:%02d recal=%s %02d:%02d drift=%sh",
            settings.train_schedule_hour,
            settings.train_schedule_minute,
            settings.recalibrate_schedule_weekday,
            settings.recalibrate_schedule_hour,
            settings.recalibrate_schedule_minute,
            settings.drift_check_hours,
        )
        while True:
            started = time.time()
            self.run_once()
            elapsed = time.time() - started
            sleep_for = max(10, settings.monitor_loop_seconds - int(elapsed))
            time.sleep(sleep_for)
