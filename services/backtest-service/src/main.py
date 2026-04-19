from __future__ import annotations

import argparse
import logging

import uvicorn

from .app import app
from .config import settings
from .db import db
from .worker import BacktestWorker


def run_server() -> None:
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


def run_worker() -> None:
    worker = BacktestWorker(db)
    worker.run_loop()


def cmd_serve(_: argparse.Namespace) -> None:
    run_server()


def cmd_worker(_: argparse.Namespace) -> None:
    run_worker()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="backtest-service")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run backtest REST service")
    p_serve.set_defaults(func=cmd_serve)

    p_worker = sub.add_parser("worker", help="run backtest worker")
    p_worker.set_defaults(func=cmd_worker)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
