from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings
from .db import Database, interval_duration
from .features import build_feature_map
from .labeling import rsi_revert_label, triple_barrier_label

DROP_INVALID_EVENT = "invalid_event"
DROP_MISSING_INDICATOR_SNAPSHOT = "missing_indicator_snapshot"
DROP_INSUFFICIENT_RECENT_BARS = "insufficient_recent_bars"
DROP_INSUFFICIENT_FUTURE_BARS = "insufficient_future_bars"

DROP_REASON_MESSAGES = {
    DROP_INVALID_EVENT: "invalid event payload",
    DROP_MISSING_INDICATOR_SNAPSHOT: "missing indicator snapshot",
    DROP_INSUFFICIENT_RECENT_BARS: "insufficient recent candles",
    DROP_INSUFFICIENT_FUTURE_BARS: "insufficient future candles",
}


@dataclass
class SampleRow:
    event_id: int
    event_ts: datetime
    symbol: str
    interval: str
    direction: str
    features: dict[str, float]
    y_pass: int
    realized_return: float
    y_rsi_revert: int | None


@dataclass
class DatasetBuildStats:
    total_events: int = 0
    built_samples: int = 0
    positive_labels: int = 0
    negative_labels: int = 0
    dropped_invalid_event: int = 0
    dropped_missing_indicator_snapshot: int = 0
    dropped_insufficient_recent_bars: int = 0
    dropped_insufficient_future_bars: int = 0

    @property
    def positive_ratio(self) -> float:
        if self.built_samples <= 0:
            return 0.0
        return float(self.positive_labels / self.built_samples)

    def record_failure(self, reason: str) -> None:
        if reason == DROP_INVALID_EVENT:
            self.dropped_invalid_event += 1
        elif reason == DROP_MISSING_INDICATOR_SNAPSHOT:
            self.dropped_missing_indicator_snapshot += 1
        elif reason == DROP_INSUFFICIENT_RECENT_BARS:
            self.dropped_insufficient_recent_bars += 1
        elif reason == DROP_INSUFFICIENT_FUTURE_BARS:
            self.dropped_insufficient_future_bars += 1

    def record_sample(self, sample: SampleRow) -> None:
        self.built_samples += 1
        if int(sample.y_pass) > 0:
            self.positive_labels += 1
        else:
            self.negative_labels += 1


def explain_drop_reason(reason: str | None) -> str:
    if not reason:
        return "insufficient features"
    return DROP_REASON_MESSAGES.get(reason, "insufficient features")


def build_sample_for_event_with_reason(
    db: Database,
    event: dict[str, Any],
    include_label: bool,
) -> tuple[SampleRow | None, str | None]:
    exchange = str(event.get("exchange") or settings.default_exchange)
    symbol = str(event.get("symbol") or "")
    interval = str(event.get("interval") or settings.interval)
    event_ts = event.get("event_ts")

    if not symbol or not isinstance(event_ts, datetime):
        return None, DROP_INVALID_EVENT

    snapshot = db.fetch_indicator_snapshot(exchange, symbol, interval, event_ts)
    current = snapshot.get("current") or {}

    if "rsi_14" not in current or "atr_14" not in current:
        return None, DROP_MISSING_INDICATOR_SNAPSHOT

    recent = db.fetch_recent_candles(exchange, symbol, interval, event_ts, bars=max(10, settings.horizon_bars + 2))
    if len(recent) < 7:
        return None, DROP_INSUFFICIENT_RECENT_BARS

    features = build_feature_map(event, snapshot, recent)

    if not include_label:
        return (
            SampleRow(
                event_id=int(event["id"]),
                event_ts=event_ts,
                symbol=symbol,
                interval=interval,
                direction=str(event.get("direction") or ""),
                features=features,
                y_pass=0,
                realized_return=0.0,
                y_rsi_revert=None,
            ),
            None,
        )

    future = db.fetch_future_candles(exchange, symbol, interval, event_ts, bars=settings.horizon_bars)
    if len(future) < settings.horizon_bars:
        return None, DROP_INSUFFICIENT_FUTURE_BARS

    y_pass, realized = triple_barrier_label(
        event=event,
        snapshot=snapshot,
        recent_candles=recent,
        future_candles=future,
        horizon_bars=settings.horizon_bars,
        tp_atr_mult=settings.barrier_tp_atr_mult,
        sl_atr_mult=settings.barrier_sl_atr_mult,
    )
    future_rsi = db.fetch_future_rsi_values(exchange, symbol, interval, event_ts, bars=3)
    y_revert = rsi_revert_label(future_rsi)

    return (
        SampleRow(
            event_id=int(event["id"]),
            event_ts=event_ts,
            symbol=symbol,
            interval=interval,
            direction=str(event.get("direction") or ""),
            features=features,
            y_pass=int(y_pass),
            realized_return=float(realized),
            y_rsi_revert=y_revert,
        ),
        None,
    )


def build_sample_for_event(
    db: Database,
    event: dict[str, Any],
    include_label: bool,
) -> SampleRow | None:
    sample, _ = build_sample_for_event_with_reason(db, event, include_label)
    return sample


def build_training_dataset_with_stats(db: Database) -> tuple[list[SampleRow], DatasetBuildStats]:
    now = datetime.now(tz=timezone.utc)
    end_ts = now - interval_duration(settings.interval, settings.horizon_bars)
    start_ts = end_ts - timedelta(days=settings.lookback_days)

    events = db.fetch_rsi_events_for_training(
        exchange=settings.default_exchange,
        interval=settings.interval,
        symbols=settings.symbols,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    samples: list[SampleRow] = []
    stats = DatasetBuildStats(total_events=len(events))
    for event in events:
        sample, reason = build_sample_for_event_with_reason(db, event, include_label=True)
        if sample is None:
            if reason:
                stats.record_failure(reason)
            continue
        samples.append(sample)
        stats.record_sample(sample)
    return samples, stats


def build_training_dataset(db: Database) -> list[SampleRow]:
    samples, _ = build_training_dataset_with_stats(db)
    return samples
