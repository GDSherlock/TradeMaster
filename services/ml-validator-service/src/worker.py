from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings
from .dataset import build_sample_for_event_with_reason, explain_drop_reason
from .db import Database, interval_duration
from .inference import predict_validation
from .registry import load_champion_bundle

LOG = logging.getLogger(__name__)


class ValidationWorker:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _label_due_at(self, event_ts: Any, interval: str) -> datetime | None:
        if not isinstance(event_ts, datetime):
            return None
        return event_ts + interval_duration(interval, settings.horizon_bars)

    def validate_events(
        self,
        events: list[dict[str, Any]],
        champion: str | None,
        advance_cursor: bool,
    ) -> int:
        model_bundle = load_champion_bundle(champion)
        last_processed: int | None = None
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
                    "label_due_at": self._label_due_at(event.get("event_ts"), str(event.get("interval") or settings.interval)),
                    "y_rsi_revert": None,
                }
                self.db.upsert_validation(payload)
                event_id = int(event["id"])
                last_processed = event_id if last_processed is None else max(last_processed, event_id)
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
                "label_due_at": self._label_due_at(sample.event_ts, sample.interval),
                "y_rsi_revert": sample.y_rsi_revert,
            }
            self.db.upsert_validation(payload)

            last_processed = sample.event_id if last_processed is None else max(last_processed, sample.event_id)
            processed += 1

        if advance_cursor and last_processed is not None:
            self.db.upsert_runtime_state(last_processed_event_id=last_processed)

        return processed

    def revalidate_recent_candidates(
        self,
        lookback_days: int | None = None,
        limit: int | None = None,
        max_batches: int | None = None,
    ) -> int:
        started_at = datetime.now(tz=timezone.utc)
        runtime = self.db.fetch_runtime_state()
        champion = runtime.get("champion_version")
        if not champion:
            self.db.upsert_runtime_state(
                last_revalidate_at=started_at,
                last_revalidate_status="skipped",
                last_revalidate_error="no champion version",
                last_revalidate_processed_count=0,
            )
            LOG.info("ml revalidate skipped: no champion version")
            return 0

        if load_champion_bundle(champion) is None:
            self.db.upsert_runtime_state(
                last_revalidate_at=started_at,
                last_revalidate_status="skipped",
                last_revalidate_error=f"champion bundle missing: {champion}",
                last_revalidate_processed_count=0,
            )
            LOG.warning("ml revalidate skipped: champion bundle missing version=%s", champion)
            return 0

        days = max(1, lookback_days or settings.revalidate_lookback_days)
        batch_size = max(1, limit or settings.revalidate_batch_size)
        batch_limit = max(1, max_batches or settings.revalidate_max_batches)
        start_ts = datetime.now(tz=timezone.utc) - timedelta(days=days)
        total_processed = 0

        self.db.upsert_runtime_state(
            last_revalidate_at=started_at,
            last_revalidate_status="running",
            last_revalidate_error="",
            last_revalidate_processed_count=0,
        )

        try:
            for batch_no in range(1, batch_limit + 1):
                events = self.db.fetch_recent_revalidation_candidates(
                    exchange=settings.default_exchange,
                    interval=settings.interval,
                    symbols=settings.symbols,
                    start_ts=start_ts,
                    champion_version=str(champion),
                    limit=batch_size,
                )
                if not events:
                    self.db.upsert_runtime_state(
                        last_revalidate_at=datetime.now(tz=timezone.utc),
                        last_revalidate_status="succeeded",
                        last_revalidate_error="",
                        last_revalidate_processed_count=total_processed,
                    )
                    LOG.info(
                        "ml revalidate complete champion=%s lookback_days=%s batches=%s processed=%s",
                        champion,
                        days,
                        batch_no - 1,
                        total_processed,
                    )
                    return total_processed

                processed = self.validate_events(events, champion=str(champion), advance_cursor=False)
                total_processed += processed
                LOG.info(
                    "ml revalidate batch champion=%s batch=%s requested=%s processed=%s total=%s",
                    champion,
                    batch_no,
                    len(events),
                    processed,
                    total_processed,
                )

            remaining = self.db.fetch_recent_revalidation_candidates(
                exchange=settings.default_exchange,
                interval=settings.interval,
                symbols=settings.symbols,
                start_ts=start_ts,
                champion_version=str(champion),
                limit=1,
            )
            status = "partial" if remaining else "succeeded"
            error = (
                f"revalidation stopped after {batch_limit} batches with remaining candidates"
                if remaining
                else ""
            )
            self.db.upsert_runtime_state(
                last_revalidate_at=datetime.now(tz=timezone.utc),
                last_revalidate_status=status,
                last_revalidate_error=error,
                last_revalidate_processed_count=total_processed,
            )
            if remaining:
                LOG.warning(
                    "ml revalidate partial champion=%s lookback_days=%s batch_limit=%s processed=%s",
                    champion,
                    days,
                    batch_limit,
                    total_processed,
                )
            return total_processed
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.db.upsert_runtime_state(
                last_revalidate_at=datetime.now(tz=timezone.utc),
                last_revalidate_status="failed",
                last_revalidate_error=message[:500],
                last_revalidate_processed_count=total_processed,
            )
            raise

    def run_once(self) -> int:
        runtime = self.db.fetch_runtime_state()
        last_processed = int(runtime.get("last_processed_event_id") or 0)
        champion = runtime.get("champion_version")

        events = self.db.fetch_unvalidated_rsi_events(
            exchange=settings.default_exchange,
            interval=settings.interval,
            symbols=settings.symbols,
            since_id=last_processed,
            limit=settings.validate_batch_size,
        )

        if not events:
            return 0

        return self.validate_events(events, champion=champion, advance_cursor=True)

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
