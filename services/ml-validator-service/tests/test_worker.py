from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "dev-token")

try:
    from src.dataset import SampleRow  # noqa: E402
    from src.worker import ValidationWorker  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    SampleRow = None
    ValidationWorker = None


class FakeDb:
    def __init__(self, champion_version: str | None = "champion_v2") -> None:
        self.runtime = {
            "champion_version": champion_version,
            "last_processed_event_id": 999,
        }
        self.validation_payloads: list[dict] = []
        self.runtime_updates: list[dict] = []
        self.fetch_args: dict | None = None
        self.fetch_calls = 0

    def fetch_runtime_state(self) -> dict:
        return dict(self.runtime)

    def fetch_recent_revalidation_candidates(self, **kwargs) -> list[dict]:
        self.fetch_args = dict(kwargs)
        self.fetch_calls += 1
        now = datetime.now(tz=timezone.utc)
        if self.fetch_calls == 2:
            return []
        return [
            {
                "id": 501,
                "exchange": "binance_futures_um",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "rule_key": "RSI_OVERSOLD",
                "direction": "long",
                "event_ts": now,
                "detected_at": now,
                "score": 0.8,
                "cooldown_seconds": 900,
                "payload": {},
            }
        ]

    def upsert_validation(self, payload: dict) -> None:
        self.validation_payloads.append(dict(payload))

    def upsert_runtime_state(self, **kwargs) -> None:
        self.runtime_updates.append(dict(kwargs))


@unittest.skipIf(ValidationWorker is None, "worker dependencies are not installed in current environment")
class TestValidationWorker(unittest.TestCase):
    @patch("src.worker.predict_validation")
    @patch("src.worker.build_sample_for_event_with_reason")
    @patch("src.worker.load_champion_bundle")
    def test_revalidate_recent_candidates_uses_champion_without_advancing_cursor(
        self,
        mock_load_bundle,
        mock_build_sample,
        mock_predict,
    ) -> None:
        db = FakeDb()
        now = datetime.now(tz=timezone.utc)
        mock_load_bundle.return_value = object()
        mock_build_sample.return_value = (
            SampleRow(
                event_id=501,
                event_ts=now,
                symbol="BTCUSDT",
                interval="1h",
                direction="long",
                features={"rsi_current": 30.0},
                y_pass=0,
                realized_return=0.0,
                y_rsi_revert=None,
            ),
            None,
        )
        mock_predict.return_value = {
            "model_name": "rsi_lr_calibrated",
            "model_version": "champion_v2",
            "probability": 0.74,
            "threshold": 0.55,
            "decision": "passed",
            "reason": "probability above threshold",
            "top_features": [{"name": "rsi_current", "value": 30.0}],
        }

        processed = ValidationWorker(db).revalidate_recent_candidates(lookback_days=3, limit=10)

        self.assertEqual(processed, 1)
        self.assertEqual(len(db.validation_payloads), 1)
        self.assertEqual(db.validation_payloads[0]["model_version"], "champion_v2")
        self.assertGreaterEqual(len(db.runtime_updates), 2)
        self.assertEqual(db.runtime_updates[0]["last_revalidate_status"], "running")
        self.assertEqual(db.runtime_updates[-1]["last_revalidate_status"], "succeeded")
        self.assertEqual(db.runtime_updates[-1]["last_revalidate_processed_count"], 1)
        for update in db.runtime_updates:
            self.assertNotIn("last_processed_event_id", update)
        self.assertIsNotNone(db.fetch_args)
        self.assertEqual(db.fetch_args["champion_version"], "champion_v2")
        self.assertEqual(db.fetch_args["limit"], 10)

    def test_revalidate_recent_candidates_skips_when_champion_missing(self) -> None:
        db = FakeDb(champion_version=None)
        processed = ValidationWorker(db).revalidate_recent_candidates()
        self.assertEqual(processed, 0)
        self.assertEqual(db.validation_payloads, [])
        self.assertIsNone(db.fetch_args)
        self.assertEqual(db.runtime_updates[-1]["last_revalidate_status"], "skipped")

    @patch("src.worker.predict_validation")
    @patch("src.worker.build_sample_for_event_with_reason")
    @patch("src.worker.load_champion_bundle")
    def test_revalidate_recent_candidates_stops_at_batch_cap(
        self,
        mock_load_bundle,
        mock_build_sample,
        mock_predict,
    ) -> None:
        class MultiBatchDb(FakeDb):
            def fetch_recent_revalidation_candidates(self, **kwargs) -> list[dict]:
                self.fetch_args = dict(kwargs)
                self.fetch_calls += 1
                now = datetime.now(tz=timezone.utc)
                if self.fetch_calls <= 3:
                    return [
                        {
                            "id": 500 + self.fetch_calls,
                            "exchange": "binance_futures_um",
                            "symbol": "BTCUSDT",
                            "interval": "1h",
                            "rule_key": "RSI_OVERSOLD",
                            "direction": "long",
                            "event_ts": now,
                            "detected_at": now,
                            "score": 0.8,
                            "cooldown_seconds": 900,
                            "payload": {},
                        }
                    ]
                return []

        db = MultiBatchDb()
        now = datetime.now(tz=timezone.utc)
        mock_load_bundle.return_value = object()
        mock_build_sample.return_value = (
            SampleRow(
                event_id=501,
                event_ts=now,
                symbol="BTCUSDT",
                interval="1h",
                direction="long",
                features={"rsi_current": 30.0},
                y_pass=0,
                realized_return=0.0,
                y_rsi_revert=None,
            ),
            None,
        )
        mock_predict.return_value = {
            "model_name": "rsi_lr_calibrated",
            "model_version": "champion_v2",
            "probability": 0.74,
            "threshold": 0.55,
            "decision": "passed",
            "reason": "probability above threshold",
            "top_features": [{"name": "rsi_current", "value": 30.0}],
        }

        processed = ValidationWorker(db).revalidate_recent_candidates(lookback_days=3, limit=10, max_batches=2)

        self.assertEqual(processed, 2)
        self.assertEqual(db.runtime_updates[-1]["last_revalidate_status"], "partial")
        self.assertIn("remaining candidates", db.runtime_updates[-1]["last_revalidate_error"])


if __name__ == "__main__":
    unittest.main()
