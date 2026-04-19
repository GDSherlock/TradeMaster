from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ["AUTH_ENABLED"] = "false"
os.environ["API_TOKEN"] = "test-token"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from src import app as app_module
from src.auth import enforce_http_auth
from starlette.requests import Request


class FakeDb:
    def __init__(self) -> None:
        self.created_strategy_payloads: list[dict] = []
        self.created_runs: list[dict] = []

    def list_symbols(self, exchange: str) -> list[str]:
        return ["BTCUSDT", "ETHUSDT"]

    def list_signal_rules(self) -> list[str]:
        return ["RSI_OVERSOLD", "RSI_OVERBOUGHT"]

    def list_strategies(self) -> list[dict]:
        return [
            {
                "id": 1,
                "name": "Mean Reversion",
                "description": "Test strategy",
                "latest_version_id": 11,
                "latest_version_no": 2,
                "exchange": "binance_futures_um",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "dsl": {},
                "latest_version_created_at": "2024-01-02T00:00:00+00:00",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-02T00:00:00+00:00",
            }
        ]

    def get_strategy(self, strategy_id: int) -> dict | None:
        return self.list_strategies()[0] if strategy_id == 1 else None

    def list_strategy_versions(self, strategy_id: int) -> list[dict]:
        if strategy_id != 1:
            return []
        return [
            {
                "id": 11,
                "strategy_id": 1,
                "version_no": 2,
                "exchange": "binance_futures_um",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "dsl": {
                    "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
                    "exit": {"logic": "any", "clauses": []},
                    "sizing": {"equity_pct": 0.25, "leverage": 2.0, "direction_mode": "long"},
                    "costs": {"fee_bps": 4.0, "slippage_bps": 2.0},
                    "drawdown": {"max_total_drawdown_pct": 0.15, "trailing_drawdown_pct": 0.1, "action": "flatten_and_halt"},
                    "execution": {"fill_policy": "current_bar_close"},
                },
                "created_at": "2024-01-02T00:00:00+00:00",
            }
        ]

    def create_strategy_version(self, **payload) -> dict:
        self.created_strategy_payloads.append(payload)
        return {
            "strategy_id": payload.get("strategy_id") or 1,
            "name": payload["name"],
            "description": payload["description"],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "version": self.list_strategy_versions(1)[0],
        }

    def get_strategy_version(self, version_id: int) -> dict | None:
        return self.list_strategy_versions(1)[0] if version_id == 11 else None

    def create_run(self, strategy_version: dict, exchange: str, symbol: str, interval: str, start_ts, end_ts, run_params: dict) -> dict:
        self.created_runs.append(
            {
                "strategy_version": strategy_version,
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "run_params": run_params,
            }
        )
        return {
            "id": 101,
            "strategy_id": 1,
            "strategy_version_id": strategy_version["id"],
            "version_no": strategy_version["version_no"],
            "strategy_name": "Mean Reversion",
            "strategy_description": "Test strategy",
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "start_ts": start_ts.isoformat(),
            "end_ts": end_ts.isoformat(),
            "status": "queued",
            "run_params": run_params,
            "summary": {},
            "error_code": None,
            "error_message": None,
            "queued_at": "2024-01-03T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "canceled_at": None,
            "created_at": "2024-01-03T00:00:00+00:00",
            "updated_at": "2024-01-03T00:00:00+00:00",
        }

    def list_runs(self, limit: int = 100) -> list[dict]:
        return []

    def get_run(self, run_id: int) -> dict | None:
        if run_id != 101:
            return None
        return {
            "id": 101,
            "strategy_id": 1,
            "strategy_version_id": 11,
            "version_no": 2,
            "strategy_name": "Mean Reversion",
            "strategy_description": "Test strategy",
            "exchange": "binance_futures_um",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "start_ts": "2024-01-01T00:00:00+00:00",
            "end_ts": "2024-01-03T00:00:00+00:00",
            "status": "queued",
            "run_params": {},
            "summary": {},
            "error_code": None,
            "error_message": None,
            "queued_at": "2024-01-03T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "canceled_at": None,
            "created_at": "2024-01-03T00:00:00+00:00",
            "updated_at": "2024-01-03T00:00:00+00:00",
        }

    def get_run_equity(self, run_id: int) -> list[dict]:
        return []

    def get_run_trades(self, run_id: int) -> list[dict]:
        return []

    def cancel_run(self, run_id: int) -> dict | None:
        return self.get_run(run_id)


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_db = FakeDb()
        self.db_patch = patch.object(app_module, "db", self.fake_db)
        self.db_patch.start()

    def tearDown(self) -> None:
        self.db_patch.stop()
        object.__setattr__(app_module.settings, "auth_enabled", False)
        object.__setattr__(app_module.settings, "api_token", "test-token")

    def _make_request(self, path: str, payload: dict | None = None, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def read_json():
            return payload

        request = Request(
            {
                "type": "http",
                "method": "POST" if payload is not None else "GET",
                "path": path,
                "headers": headers or [],
                "query_string": b"",
            },
            receive=receive,
        )
        if payload is not None:
            request.json = read_json  # type: ignore[method-assign]
        return request

    def test_catalog_and_strategy_creation_and_run_queue(self) -> None:
        catalog_response = app_module.backtest_catalog()
        self.assertEqual(catalog_response["code"], "0")
        self.assertIn("BTCUSDT", catalog_response["data"]["symbols"])

        strategy_response = asyncio.run(
            app_module.create_strategy(
                self._make_request(
                    "/backtest/strategies",
                    {
                "name": "Mean Reversion",
                "description": "Test strategy",
                "exchange": "binance_futures_um",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "dsl": {
                    "entry": {"logic": "all", "clauses": [{"type": "signal_rule", "side": "long", "rule_key": "RSI_OVERSOLD"}]},
                    "exit": {"logic": "any", "clauses": []},
                    "sizing": {"equity_pct": 0.25, "leverage": 2, "direction_mode": "long"},
                    "costs": {"fee_bps": 4, "slippage_bps": 2},
                    "drawdown": {"max_total_drawdown_pct": 0.15, "trailing_drawdown_pct": 0.1, "action": "flatten_and_halt"},
                    "execution": {"fill_policy": "current_bar_close"},
                },
                    },
                )
            )
        )
        self.assertEqual(strategy_response["code"], "0")
        self.assertEqual(self.fake_db.created_strategy_payloads[0]["symbol"], "BTCUSDT")

        run_response = asyncio.run(
            app_module.create_run(
                self._make_request(
                    "/backtest/runs",
                    {
                "strategy_version_id": 11,
                "start_ts": "2024-01-01T00:00:00Z",
                "end_ts": "2024-01-03T00:00:00Z",
                    },
                )
            )
        )
        self.assertEqual(run_response["code"], "0")
        self.assertEqual(run_response["data"]["status"], "queued")
        self.assertEqual(self.fake_db.created_runs[0]["strategy_version"]["id"], 11)

    def test_auth_guard_rejects_missing_token_when_enabled(self) -> None:
        object.__setattr__(app_module.settings, "auth_enabled", True)
        object.__setattr__(app_module.settings, "api_token", "secret-token")

        with self.assertRaises(HTTPException):
            enforce_http_auth(self._make_request("/backtest/catalog"))

        enforce_http_auth(
            self._make_request(
                "/backtest/catalog",
                headers=[(b"x-api-token", b"secret-token")],
            )
        )


if __name__ == "__main__":
    unittest.main()
