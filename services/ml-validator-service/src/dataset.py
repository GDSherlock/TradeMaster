from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings
from .db import Database
from .features import build_feature_map
from .labeling import rsi_revert_label, triple_barrier_label


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


def build_sample_for_event(
    db: Database,
    event: dict[str, Any],
    include_label: bool,
) -> SampleRow | None:
    exchange = str(event.get("exchange") or settings.default_exchange)
    symbol = str(event.get("symbol") or "")
    interval = str(event.get("interval") or settings.interval)
    event_ts = event.get("event_ts")

    if not symbol or not isinstance(event_ts, datetime):
        return None

    snapshot = db.fetch_indicator_snapshot(exchange, symbol, interval, event_ts)
    current = snapshot.get("current") or {}

    if "rsi_14" not in current or "atr_14" not in current:
        return None

    recent = db.fetch_recent_candles(exchange, symbol, interval, event_ts, bars=max(10, settings.horizon_bars + 2))
    if len(recent) < 7:
        return None

    features = build_feature_map(event, snapshot, recent)

    if not include_label:
        return SampleRow(
            event_id=int(event["id"]),
            event_ts=event_ts,
            symbol=symbol,
            interval=interval,
            direction=str(event.get("direction") or ""),
            features=features,
            y_pass=0,
            realized_return=0.0,
            y_rsi_revert=None,
        )

    future = db.fetch_future_candles(exchange, symbol, interval, event_ts, bars=settings.horizon_bars)
    if len(future) < settings.horizon_bars:
        return None

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

    return SampleRow(
        event_id=int(event["id"]),
        event_ts=event_ts,
        symbol=symbol,
        interval=interval,
        direction=str(event.get("direction") or ""),
        features=features,
        y_pass=int(y_pass),
        realized_return=float(realized),
        y_rsi_revert=y_revert,
    )


def build_training_dataset(db: Database) -> list[SampleRow]:
    now = datetime.now(tz=timezone.utc)
    end_ts = now - timedelta(hours=settings.horizon_bars)
    start_ts = end_ts - timedelta(days=settings.lookback_days)

    events = db.fetch_rsi_events_for_training(
        exchange=settings.default_exchange,
        interval=settings.interval,
        symbols=settings.symbols,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    samples: list[SampleRow] = []
    for event in events:
        sample = build_sample_for_event(db, event, include_label=True)
        if sample is None:
            continue
        samples.append(sample)
    return samples
