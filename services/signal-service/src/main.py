from __future__ import annotations

import argparse
import logging
import threading
import time

import uvicorn

from .config import settings
from .engine import run_once

LOG = logging.getLogger(__name__)


def _parse_csv(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def _parse_intervals(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return [x.strip().lower() for x in fallback]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def run_loop(symbols: list[str], intervals: list[str]) -> None:
    LOG.info("signal engine loop started schedule=%ss", settings.schedule_seconds)
    while True:
        started = time.time()
        try:
            run_once(symbols=symbols, intervals=intervals)
        except Exception:  # noqa: BLE001
            LOG.exception("signal engine run failed")
        elapsed = time.time() - started
        sleep_for = max(1, settings.schedule_seconds - int(elapsed))
        time.sleep(sleep_for)


def run_server() -> None:
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


def cmd_serve(_: argparse.Namespace) -> None:
    run_server()


def cmd_engine(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    intervals = _parse_intervals(args.intervals, settings.intervals)
    if args.once:
        run_once(symbols=symbols, intervals=intervals)
        return
    run_loop(symbols=symbols, intervals=intervals)


def cmd_all(args: argparse.Namespace) -> None:
    symbols = _parse_csv(args.symbols, settings.symbols)
    intervals = _parse_intervals(args.intervals, settings.intervals)

    thread = threading.Thread(target=lambda: run_loop(symbols=symbols, intervals=intervals), daemon=True)
    thread.start()
    run_server()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="signal-service")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run signal REST/WS service")
    p_serve.set_defaults(func=cmd_serve)

    p_engine = sub.add_parser("engine", help="run signal rule engine")
    p_engine.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_engine.add_argument("--intervals", type=str, default=",".join(settings.intervals))
    p_engine.add_argument("--once", action="store_true")
    p_engine.set_defaults(func=cmd_engine)

    p_all = sub.add_parser("all", help="run engine loop and REST/WS service")
    p_all.add_argument("--symbols", type=str, default=",".join(settings.symbols))
    p_all.add_argument("--intervals", type=str, default=",".join(settings.intervals))
    p_all.set_defaults(func=cmd_all)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
