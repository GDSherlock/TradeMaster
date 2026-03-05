from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

# Avoid requiring a production token in unit test imports.
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "dev-token")

from src.response import api_response  # noqa: E402
from src.routers.ml import _format_training_run  # noqa: E402
from src.routers.signal import _event_to_api_item  # noqa: E402


class ApiContractShapeTests(unittest.TestCase):
    def test_api_response_envelope_shape(self) -> None:
        payload = api_response({"status": "ok"})
        self.assertSetEqual(set(payload.keys()), {"code", "msg", "success", "data"})
        self.assertEqual(payload["code"], "0")
        self.assertTrue(payload["success"])

    def test_signal_event_shape(self) -> None:
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": 101,
            "exchange": "binance_futures_um",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "rule_key": "RSI_OVERSOLD",
            "signal_type": "signal",
            "direction": "long",
            "event_ts": now,
            "detected_at": now,
            "price": 62000.0,
            "score": 0.91,
            "cooldown_seconds": 900,
            "cooldown_left_seconds": 120,
            "detail": "detail",
            "payload": {"foo": "bar"},
        }
        item = _event_to_api_item(row)
        expected_keys = {
            "id",
            "key",
            "exchange",
            "symbol",
            "interval",
            "rule_key",
            "type",
            "signal_type",
            "direction",
            "event_ts",
            "detected_at",
            "timestamp",
            "detected_timestamp",
            "price",
            "score",
            "cooldown_seconds",
            "cooldown_left_seconds",
            "detail",
            "payload",
        }
        self.assertSetEqual(set(item.keys()), expected_keys)
        self.assertEqual(item["symbol"], "BTCUSDT")
        self.assertEqual(item["rule_key"], "RSI_OVERSOLD")

    def test_ml_training_run_shape(self) -> None:
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": 1,
            "model_name": "rsi_lr_calibrated",
            "model_version": "v1",
            "train_start": now,
            "train_end": now,
            "val_start": now,
            "val_end": now,
            "test_start": now,
            "test_end": now,
            "sample_count": 1200,
            "positive_ratio": 0.3,
            "threshold": 0.55,
            "metrics_json": {"test": {"precision": 0.8}},
            "promoted": True,
            "notes": "ok",
            "run_type": "train",
            "features_used": ["rsi_current"],
            "feature_importance": [{"name": "rsi_current", "coef": 0.1}],
            "created_at": now,
        }
        item = _format_training_run(row)
        expected_keys = {
            "id",
            "model_name",
            "model_version",
            "train_start",
            "train_end",
            "val_start",
            "val_end",
            "test_start",
            "test_end",
            "sample_count",
            "positive_ratio",
            "threshold",
            "metrics",
            "promoted",
            "notes",
            "run_type",
            "features_used",
            "feature_importance",
            "created_at",
        }
        self.assertSetEqual(set(item.keys()), expected_keys)
        self.assertEqual(item["model_version"], "v1")
        self.assertTrue(item["promoted"])


if __name__ == "__main__":
    unittest.main()
