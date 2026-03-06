from __future__ import annotations

import argparse
import asyncio
import logging
import threading
from datetime import datetime, timezone

import uvicorn

from .backfill import run_backfill
from .config import settings
from .indicator_engine import run_once
from .live_ws import run_live
from .scheduler import Scheduler
from .state_store import state_store

LOG = logging.getLogger(__name__)


def _parse_csv(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def _parse_intervals(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return [x.strip().lower() for x in fallback]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _parse_optional_ts(raw: str | None) -> datetime | None:
    if not raw or not raw.strip():
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def start_health_server() -> None:
    config = uvicorn.Config(
        "src.health:app",
        host=settings.pipeline_host,
        port=settings.pipeline_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()


def cmd_backfill(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    intervals = _parse_intervals(args.intervals, settings.intervals)
    run_backfill(
        symbols=symbols,
        days=args.days,
        resume=bool(args.resume),
        chunk_rows=settings.backfill_chunk_rows,
        start_ts=_parse_optional_ts(args.start_ts),
        end_ts=_parse_optional_ts(args.end_ts),
        live_guard_minutes=args.live_guard_minutes,
        with_indicators=bool(args.with_indicators),
        db_batch_rows=args.db_batch_rows,
        intervals=intervals,
    )


def cmd_live(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    start_health_server()
    asyncio.run(run_live(symbols=symbols))


def cmd_indicator(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    intervals = _parse_intervals(args.intervals, settings.intervals)
    start_health_server()
    if args.once:
        run_once(symbols=symbols, intervals=intervals)
        return

    sched = Scheduler(
        interval_seconds=settings.indicator_schedule_seconds,
        name="indicator",
        job=lambda: run_once(symbols=symbols, intervals=intervals),
    )
    sched.run_forever()


def cmd_all(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    intervals = _parse_intervals(args.intervals, settings.intervals)

    start_health_server()
    try:
        run_backfill(
            symbols=symbols,
            days=settings.backfill_days,
            resume=True,
            chunk_rows=settings.backfill_chunk_rows,
            live_guard_minutes=settings.backfill_live_guard_minutes,
            with_indicators=False,
            db_batch_rows=settings.backfill_db_batch_rows,
            intervals=intervals,
        )
    except Exception:  # noqa: BLE001
        LOG.exception("startup backfill failed, continue with live")

    indicator_thread = threading.Thread(
        target=lambda: Scheduler(
            interval_seconds=settings.indicator_schedule_seconds,
            name="indicator",
            job=lambda: run_once(symbols=symbols, intervals=intervals),
        ).run_forever(),
        daemon=True,
    )
    indicator_thread.start()

    asyncio.run(run_live(symbols=symbols))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pipeline-service")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backfill = sub.add_parser("backfill", help="run historical backfill")
    p_backfill.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_backfill.add_argument("--days", type=int, default=settings.backfill_days)
    p_backfill.add_argument("--resume", type=int, choices=[0, 1], default=1)
    p_backfill.add_argument("--intervals", type=str, default=",".join(settings.intervals))
    p_backfill.add_argument("--start-ts", type=str, default=settings.backfill_start_ts)
    p_backfill.add_argument("--end-ts", type=str, default=settings.backfill_end_ts)
    p_backfill.add_argument("--live-guard-minutes", type=int, default=settings.backfill_live_guard_minutes)
    p_backfill.add_argument(
        "--with-indicators",
        type=int,
        choices=[0, 1],
        default=1 if settings.backfill_with_indicators else 0,
    )
    p_backfill.add_argument("--db-batch-rows", type=int, default=settings.backfill_db_batch_rows)
    p_backfill.set_defaults(func=cmd_backfill)

    p_live = sub.add_parser("live", help="run websocket live collector")
    p_live.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_live.set_defaults(func=cmd_live)

    p_indicator = sub.add_parser("indicator", help="run indicator engine")
    p_indicator.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_indicator.add_argument("--intervals", type=str, default=",".join(settings.intervals))
    p_indicator.add_argument("--once", action="store_true")
    p_indicator.set_defaults(func=cmd_indicator)

    p_all = sub.add_parser("all", help="run full pipeline")
    p_all.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_all.add_argument("--intervals", type=str, default=",".join(settings.intervals))
    p_all.set_defaults(func=cmd_all)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    state_store.heartbeat("pipeline", status="running", message=f"cmd={args.command}")
    args.func(args)


if __name__ == "__main__":
    main()
