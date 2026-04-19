from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

os.environ["AUTH_ENABLED"] = "false"
os.environ["API_TOKEN"] = "test-token"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.worker import BacktestWorker


class FakeWorkerDb:
    def __init__(self) -> None:
        self.completed: dict | None = None
        self.failed: tuple[str, str] | None = None
        self.canceled = False

    def get_strategy_version(self, version_id: int) -> dict | None:
        return {
            "id": version_id,
            "strategy_id": 1,
            "version_no": 1,
            "exchange": "binance_futures_um",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "dsl": {
                "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
                "exit": {"logic": "any", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERBOUGHT"}]},
                "sizing": {"equity_pct": 1.0, "leverage": 1.0, "direction_mode": "long"},
                "costs": {"fee_bps": 0.0, "slippage_bps": 0.0},
                "drawdown": {"max_total_drawdown_pct": 0.5, "trailing_drawdown_pct": 0.5, "action": "flatten_and_halt"},
                "execution": {"fill_policy": "current_bar_close"},
            },
            "created_at": "2024-01-01T00:00:00+00:00",
        }

    def fetch_bars_with_indicators(self, **kwargs) -> list[dict]:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return [
            {
                "ts": start,
                "close": 100.0,
                "indicators": {
                    "rsi_14": {"rsi_14": 40.0},
                    "ema_20": {"ema_20": 100.0},
                    "ema_50": {"ema_50": 100.0},
                },
            },
            {
                "ts": start + timedelta(hours=1),
                "close": 101.0,
                "indicators": {
                    "rsi_14": {"rsi_14": 25.0},
                    "ema_20": {"ema_20": 102.0},
                    "ema_50": {"ema_50": 100.0},
                },
            },
            {
                "ts": start + timedelta(hours=2),
                "close": 106.0,
                "indicators": {
                    "rsi_14": {"rsi_14": 75.0},
                    "ema_20": {"ema_20": 103.0},
                    "ema_50": {"ema_50": 100.0},
                },
            },
        ]

    def is_run_canceled(self, run_id: int) -> bool:
        return False

    def store_run_result(self, run_id: int, summary: dict, trades: list[dict], equity_points: list[dict], events: list[dict]) -> None:
        self.completed = {
            "run_id": run_id,
            "summary": summary,
            "trades": trades,
            "equity_points": equity_points,
            "events": events,
        }

    def mark_run_failed(self, run_id: int, error_code: str, error_message: str) -> None:
        self.failed = (error_code, error_message)

    def mark_run_canceled(self, run_id: int) -> None:
        self.canceled = True


class WorkerTests(unittest.TestCase):
    def test_worker_processes_queued_run(self) -> None:
        fake_db = FakeWorkerDb()
        worker = BacktestWorker(fake_db)
        worker._process_run(
            {
                "id": 501,
                "strategy_version_id": 11,
                "exchange": "binance_futures_um",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "start_ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "end_ts": datetime(2024, 1, 3, tzinfo=timezone.utc),
                "run_params": {"initial_equity": 10000.0},
            }
        )

        self.assertIsNone(fake_db.failed)
        self.assertFalse(fake_db.canceled)
        self.assertIsNotNone(fake_db.completed)
        assert fake_db.completed is not None
        self.assertEqual(fake_db.completed["run_id"], 501)
        self.assertEqual(len(fake_db.completed["trades"]), 1)
        self.assertGreater(fake_db.completed["summary"]["total_return_pct"], 0)


if __name__ == "__main__":
    unittest.main()
