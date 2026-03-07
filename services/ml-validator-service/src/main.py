from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn

from .config import settings
from .db import db
from .drift import run_drift_check_once
from .monitor import MonitorScheduler
from .recalibration import run_recalibration_once
from .trainer import run_train_once
from .worker import ValidationWorker

LOG = logging.getLogger(__name__)


def run_server() -> None:
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


def run_validate_loop() -> None:
    worker = ValidationWorker(db)
    worker.run_loop()


def run_train_loop() -> None:
    LOG.info(
        "ml train loop started schedule=%02d:%02d every %ss",
        settings.train_schedule_hour,
        settings.train_schedule_minute,
        settings.train_loop_seconds,
    )
    last_run_day: str | None = None

    while True:
        try:
            tz = ZoneInfo(settings.train_timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz=tz)
        day_key = now.strftime("%Y-%m-%d")
        should_run = (
            now.hour == settings.train_schedule_hour
            and now.minute >= settings.train_schedule_minute
            and day_key != last_run_day
        )

        if should_run:
            try:
                result = run_train_once(db)
                last_run_day = day_key
                LOG.info(
                    "ml train done run_id=%s version=%s promoted=%s threshold=%.4f",
                    result.run_id,
                    result.model_version,
                    result.promoted,
                    result.threshold,
                )
            except Exception:  # noqa: BLE001
                LOG.exception("ml train failed")

        time.sleep(max(30, settings.train_loop_seconds))


def run_recalibration_loop() -> None:
    LOG.info(
        "ml recalibration loop started weekday=%s schedule=%02d:%02d every %ss",
        settings.recalibrate_schedule_weekday,
        settings.recalibrate_schedule_hour,
        settings.recalibrate_schedule_minute,
        settings.train_loop_seconds,
    )
    last_run_week: str | None = None

    while True:
        try:
            tz = ZoneInfo(settings.train_timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz=tz)
        week_key = now.strftime("%G-%V")
        should_run = (
            now.weekday() == settings.recalibrate_schedule_weekday
            and now.hour == settings.recalibrate_schedule_hour
            and now.minute >= settings.recalibrate_schedule_minute
            and week_key != last_run_week
        )

        if should_run:
            try:
                result = run_recalibration_once(db)
                last_run_week = week_key
                LOG.info(
                    "ml recalibration done id=%s promoted=%s old=%.4f new=%.4f",
                    result.recalibration_id,
                    result.promoted,
                    result.old_threshold,
                    result.new_threshold,
                )
            except Exception:  # noqa: BLE001
                LOG.exception("ml recalibration failed")

        time.sleep(max(30, settings.train_loop_seconds))


def run_drift_check_loop() -> None:
    LOG.info("ml drift-check loop started every %sh", settings.drift_check_hours)
    while True:
        try:
            result = run_drift_check_once(db, auto_retrain=True)
            LOG.info(
                "ml drift-check done check_id=%s version=%s max_psi=%.4f triggered=%s",
                result.check_id,
                result.champion_version,
                result.max_feature_psi,
                result.triggered_retrain,
            )
        except Exception:  # noqa: BLE001
            LOG.exception("ml drift-check failed")
        time.sleep(max(60, settings.drift_check_hours * 3600))


def run_monitor_loop() -> None:
    scheduler = MonitorScheduler(db)
    scheduler.run_loop()


def cmd_serve(_: argparse.Namespace) -> None:
    run_server()


def cmd_validate(args: argparse.Namespace) -> None:
    worker = ValidationWorker(db)
    if args.once:
        processed = worker.run_once()
        LOG.info("ml validate once processed=%s", processed)
        return
    worker.run_loop()


def cmd_train(args: argparse.Namespace) -> None:
    if args.once:
        result = run_train_once(db)
        LOG.info(
            "ml train once run_id=%s version=%s promoted=%s val_precision=%.4f test_precision=%.4f",
            result.run_id,
            result.model_version,
            result.promoted,
            result.val_precision,
            result.test_precision,
        )
        return
    run_train_loop()


def cmd_train_loop(_: argparse.Namespace) -> None:
    run_train_loop()


def cmd_recalibrate(args: argparse.Namespace) -> None:
    if args.once:
        result = run_recalibration_once(db)
        LOG.info(
            "ml recalibration once id=%s version=%s promoted=%s old=%.4f new=%.4f",
            result.recalibration_id,
            result.champion_version,
            result.promoted,
            result.old_threshold,
            result.new_threshold,
        )
        return
    run_recalibration_loop()


def cmd_drift_check(args: argparse.Namespace) -> None:
    if args.once:
        result = run_drift_check_once(db, auto_retrain=True)
        LOG.info(
            "ml drift-check once check_id=%s version=%s sample_count=%s max_psi=%.4f triggered=%s",
            result.check_id,
            result.champion_version,
            result.sample_count,
            result.max_feature_psi,
            result.triggered_retrain,
        )
        return
    run_drift_check_loop()


def cmd_monitor_loop(_: argparse.Namespace) -> None:
    run_monitor_loop()


def cmd_revalidate(_: argparse.Namespace) -> None:
    worker = ValidationWorker(db)
    processed = worker.revalidate_recent_candidates()
    LOG.info("ml revalidate once processed=%s", processed)


def cmd_all(_: argparse.Namespace) -> None:
    validate_thread = threading.Thread(target=run_validate_loop, daemon=True)
    validate_thread.start()
    monitor_thread = threading.Thread(target=run_monitor_loop, daemon=True)
    monitor_thread.start()
    run_server()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ml-validator-service")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run ml-validator REST service")
    p_serve.set_defaults(func=cmd_serve)

    p_validate = sub.add_parser("validate", help="run validation worker")
    p_validate.add_argument("--once", action="store_true", help="run once and exit")
    p_validate.set_defaults(func=cmd_validate)

    p_train = sub.add_parser("train", help="run training")
    p_train.add_argument("--once", action="store_true", help="run once and exit")
    p_train.set_defaults(func=cmd_train)

    p_train_loop = sub.add_parser("train-loop", help="run daily training scheduler")
    p_train_loop.set_defaults(func=cmd_train_loop)

    p_recalibrate = sub.add_parser("recalibrate", help="run threshold recalibration")
    p_recalibrate.add_argument("--once", action="store_true", help="run once and exit")
    p_recalibrate.set_defaults(func=cmd_recalibrate)

    p_drift = sub.add_parser("drift-check", help="run feature drift check")
    p_drift.add_argument("--once", action="store_true", help="run once and exit")
    p_drift.set_defaults(func=cmd_drift_check)

    p_monitor = sub.add_parser("monitor-loop", help="run combined train/recalibrate/drift scheduler")
    p_monitor.set_defaults(func=cmd_monitor_loop)

    p_revalidate = sub.add_parser("revalidate", help="revalidate recent candidates with current champion")
    p_revalidate.add_argument("--once", action="store_true", help="run once and exit")
    p_revalidate.set_defaults(func=cmd_revalidate)

    p_all = sub.add_parser("all", help="run validate loop + monitor loop + REST service")
    p_all.set_defaults(func=cmd_all)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
