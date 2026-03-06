from __future__ import annotations

import logging
import time
from datetime import timedelta

from .config import settings
from .dataset import build_sample_for_event_with_reason, explain_drop_reason
from .db import Database
from .inference import predict_validation
from .registry import load_champion_bundle

LOG = logging.getLogger(__name__)


class ValidationWorker:
    def __init__(self, db: Database) -> None:
        self.db = db

    def run_once(self) -> int:
        runtime = self.db.fetch_runtime_state()
        last_processed = int(runtime.get("last_processed_event_id") or 0)
        champion = runtime.get("champion_version")
        model_bundle = load_champion_bundle(champion)

        events = self.db.fetch_unvalidated_rsi_events(
            exchange=settings.default_exchange,
            interval=settings.interval,
            symbols=settings.symbols,
            since_id=last_processed,
            limit=settings.validate_batch_size,
        )

        if not events:
            return 0

        processed = 0
        for event in events:
            started = time.time()
            sample, drop_reason = build_sample_for_event_with_reason(self.db, event, include_label=False)

            if sample is None:
                payload = {
                    "event_id": int(event["id"]),
                    "exchange": event["exchange"],
                    "symbol": event["symbol"],
                    "interval": event["interval"],
                    "rule_key": event["rule_key"],
                    "direction": event["direction"],
                    "event_ts": event["event_ts"],
                    "model_name": settings.model_name,
                    "model_version": champion or "unavailable",
                    "probability": 0.0,
                    "threshold": settings.model_threshold_default,
                    "decision": "unavailable",
                    "reason": explain_drop_reason(drop_reason),
                    "features": {},
                    "top_features": [],
                    "validated_at": event.get("detected_at") or event["event_ts"],
                    "latency_ms": int((time.time() - started) * 1000),
                    "label_horizon_bars": settings.horizon_bars,
                    "label_due_at": event["event_ts"] + timedelta(hours=settings.horizon_bars),
                    "y_rsi_revert": None,
                }
                self.db.upsert_validation(payload)
                last_processed = max(last_processed, int(event["id"]))
                processed += 1
                continue

            infer = predict_validation(model_bundle, sample.features)
            payload = {
                "event_id": sample.event_id,
                "exchange": event["exchange"],
                "symbol": sample.symbol,
                "interval": sample.interval,
                "rule_key": event["rule_key"],
                "direction": sample.direction,
                "event_ts": sample.event_ts,
                "model_name": infer["model_name"],
                "model_version": infer["model_version"],
                "probability": infer["probability"],
                "threshold": infer["threshold"],
                "decision": infer["decision"],
                "reason": infer["reason"],
                "features": sample.features,
                "top_features": infer["top_features"],
                "validated_at": event.get("detected_at") or event["event_ts"],
                "latency_ms": int((time.time() - started) * 1000),
                "label_horizon_bars": settings.horizon_bars,
                "label_due_at": event["event_ts"] + timedelta(hours=settings.horizon_bars),
                "y_rsi_revert": sample.y_rsi_revert,
            }
            self.db.upsert_validation(payload)

            last_processed = max(last_processed, sample.event_id)
            processed += 1

        self.db.upsert_runtime_state(last_processed_event_id=last_processed)
        return processed

    def run_loop(self) -> None:
        while True:
            started = time.time()
            try:
                processed = self.run_once()
                LOG.info("ml validation run complete processed=%s", processed)
            except Exception:  # noqa: BLE001
                LOG.exception("ml validation run failed")

            elapsed = time.time() - started
            sleep_for = max(1, settings.validate_loop_seconds - int(elapsed))
            time.sleep(sleep_for)
