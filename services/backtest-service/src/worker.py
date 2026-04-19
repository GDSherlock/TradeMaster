from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from .config import settings
from .db import Database
from .engine import BarPoint, run_backtest

LOG = logging.getLogger(__name__)


def _used_indicators(dsl: dict[str, Any]) -> list[str]:
    indicators: set[str] = set()
    for group_name in ("entry", "exit"):
        for clause in dsl[group_name]["clauses"]:
            if clause["type"] == "signal_rule":
                indicators.update(
                    {
                        "rsi_14",
                        "ema_20",
                        "ema_50",
                        "macd_12_26_9",
                        "donchian_20",
                        "vwap",
                        "ichimoku_9_26_52",
                    }
                )
            else:
                indicators.add(clause["left"]["indicator"])
                right = clause["right"]
                if right["kind"] == "field":
                    indicators.add(right["indicator"])
    return sorted(indicators)


class BacktestWorker:
    def __init__(self, database: Database) -> None:
        self.db = database
        self._lock = threading.Lock()
        self._active_runs: set[int] = set()

    def run_loop(self) -> None:
        LOG.info(
            "backtest worker loop started poll=%.2fs max_concurrent=%s",
            settings.queue_poll_seconds,
            settings.max_concurrent_runs,
        )
        while True:
            try:
                self._fill_capacity()
            except Exception:  # noqa: BLE001
                LOG.exception("backtest worker scheduling failed")
            time.sleep(max(0.2, settings.queue_poll_seconds))

    def _fill_capacity(self) -> None:
        while True:
            with self._lock:
                capacity = settings.max_concurrent_runs - len(self._active_runs)
            if capacity <= 0:
                return

            job = self.db.claim_queued_run()
            if not job:
                return

            run_id = int(job["id"])
            with self._lock:
                self._active_runs.add(run_id)

            thread = threading.Thread(target=self._process_run, args=(job,), daemon=True)
            thread.start()

    def _process_run(self, job: dict[str, Any]) -> None:
        run_id = int(job["id"])
        try:
            strategy_version = self.db.get_strategy_version(int(job["strategy_version_id"]))
            if not strategy_version:
                self.db.mark_run_failed(run_id, "missing_strategy_version", "Run failed because the strategy version is unavailable.")
                return

            dsl = strategy_version["dsl"]
            indicators = _used_indicators(dsl)
            rows = self.db.fetch_bars_with_indicators(
                exchange=str(job["exchange"]),
                symbol=str(job["symbol"]),
                interval=str(job["interval"]),
                start_ts=job["start_ts"],
                end_ts=job["end_ts"],
                indicators=indicators,
            )
            if len(rows) < 2:
                self.db.mark_run_failed(run_id, "missing_data", "Run failed because the requested dataset is incomplete.")
                return
            if len(rows) > settings.max_bars_per_run + 1:
                self.db.mark_run_failed(run_id, "too_many_bars", "Run failed because the requested window exceeds the bar limit.")
                return

            bars = [BarPoint(ts=row["ts"], close=row["close"], indicators=row["indicators"]) for row in rows]
            result = run_backtest(
                bars=bars,
                dsl=dsl,
                start_ts=job["start_ts"],
                initial_equity=float((job.get("run_params") or {}).get("initial_equity") or settings.initial_equity),
                cancel_check=lambda: self.db.is_run_canceled(run_id),
            )

            if result["status"] == "canceled":
                self.db.mark_run_canceled(run_id)
                return

            self.db.store_run_result(
                run_id=run_id,
                summary=result["summary"],
                trades=result["trades"],
                equity_points=result["equity_points"],
                events=result["events"],
            )
            LOG.info("backtest run completed run_id=%s trades=%s", run_id, len(result["trades"]))
        except Exception:  # noqa: BLE001
            LOG.exception("backtest run failed run_id=%s", run_id)
            self.db.mark_run_failed(run_id, "internal_error", "Run failed due to an internal error.")
        finally:
            with self._lock:
                self._active_runs.discard(run_id)
