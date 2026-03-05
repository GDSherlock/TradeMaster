from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .config import settings
from .rules import RuleResult, evaluate_rule
from .storage import storage

LOG = logging.getLogger(__name__)


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_time(snapshot_ms: int | None, fallback: datetime | None) -> datetime | None:
    if snapshot_ms is not None:
        return datetime.fromtimestamp(snapshot_ms / 1000, tz=timezone.utc)
    return fallback


def _should_emit(result: RuleResult, state: dict | None, event_ts: datetime | None, now: datetime) -> bool:
    if not result.triggered:
        return False
    if event_ts is None:
        return False
    if not state:
        return True

    last_event_ts = state.get("last_event_ts")
    cooldown_until = state.get("cooldown_until")

    if isinstance(last_event_ts, datetime) and event_ts <= last_event_ts:
        return False
    if isinstance(cooldown_until, datetime) and now < cooldown_until:
        return False
    return True


def run_once(symbols: list[str] | None = None, intervals: list[str] | None = None) -> int:
    symbols = symbols or settings.symbols
    intervals = intervals or settings.intervals

    configs = storage.fetch_rule_configs(include_disabled=False)
    if not configs:
        storage.heartbeat("signal_engine", status="idle", message="no enabled rule configs")
        return 0

    targets = storage.list_targets(settings.default_exchange, symbols, intervals)
    if not targets:
        storage.heartbeat("signal_engine", status="idle", message="no indicator targets")
        return 0

    emitted = 0
    now = datetime.now(tz=timezone.utc)

    for target in targets:
        symbol = str(target["symbol"])
        interval = str(target["interval"])
        latest_ts = target.get("latest_ts")

        snapshot = storage.fetch_snapshot(settings.default_exchange, symbol, interval)
        event_ts = _event_time(snapshot.event_ts_ms, latest_ts)

        for cfg in configs:
            result = evaluate_rule(cfg, symbol, interval, snapshot)
            if result is None:
                continue

            state = storage.get_signal_state(settings.default_exchange, symbol, interval, cfg.rule_key)
            emit = _should_emit(result, state, event_ts, now)

            last_event_ts = state.get("last_event_ts") if state else None
            cooldown_until = state.get("cooldown_until") if state else None

            if emit:
                row = {
                    "exchange": settings.default_exchange,
                    "symbol": symbol,
                    "interval": interval,
                    "rule_key": result.rule_key,
                    "signal_type": result.signal_type,
                    "direction": result.direction,
                    "event_ts": event_ts,
                    "detected_at": now,
                    "price": _safe_float(snapshot.close_current),
                    "score": _safe_float(result.score),
                    "cooldown_seconds": cfg.cooldown_seconds,
                    "detail": result.detail,
                    "payload": result.payload,
                }
                storage.insert_signal_event(row)
                emitted += 1
                last_event_ts = event_ts
                cooldown_until = now + timedelta(seconds=cfg.cooldown_seconds)

            storage.upsert_signal_state(
                exchange=settings.default_exchange,
                symbol=symbol,
                interval=interval,
                rule_key=cfg.rule_key,
                last_status="on" if result.condition else "off",
                last_event_ts=last_event_ts,
                cooldown_until=cooldown_until,
                last_payload=result.payload,
            )

    storage.heartbeat("signal_engine", status="running", message=f"events={emitted} targets={len(targets)}")
    LOG.info("signal evaluation complete events=%s targets=%s", emitted, len(targets))
    return emitted
