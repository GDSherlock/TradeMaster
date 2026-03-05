from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .config import settings
from .db import Database
from .registry import load_champion_bundle

LOG = logging.getLogger(__name__)

_EPSILON = 1e-8


@dataclass
class DriftCheckResult:
    check_id: int | None
    champion_version: str | None
    sample_count: int
    overall_psi: float
    max_feature_psi: float
    triggered_retrain: bool
    triggered_run_id: int | None


def _psi(expected_pct: list[float], current_pct: list[float]) -> float:
    if len(expected_pct) != len(current_pct) or not expected_pct:
        return 0.0

    total = 0.0
    for expected, current in zip(expected_pct, current_pct):
        e = max(float(expected), _EPSILON)
        c = max(float(current), _EPSILON)
        total += (c - e) * math.log(c / e)
    return float(total)


def _distribution(values: np.ndarray, bins: list[float]) -> list[float]:
    if values.size == 0:
        return []
    if len(bins) < 2:
        return [1.0]

    hist, _ = np.histogram(values, bins=np.asarray(bins, dtype=float))
    total = int(np.sum(hist))
    if total <= 0:
        return [0.0 for _ in hist]
    return [float(v / total) for v in hist.tolist()]


def run_drift_check_once(db: Database, auto_retrain: bool = True) -> DriftCheckResult:
    runtime = db.fetch_runtime_state()
    champion_version = runtime.get("champion_version")

    if not champion_version:
        db.upsert_runtime_state(last_drift_check_at=datetime.now(tz=timezone.utc))
        return DriftCheckResult(
            check_id=None,
            champion_version=None,
            sample_count=0,
            overall_psi=0.0,
            max_feature_psi=0.0,
            triggered_retrain=False,
            triggered_run_id=None,
        )

    bundle = load_champion_bundle(champion_version)
    if bundle is None:
        db.upsert_runtime_state(last_drift_check_at=datetime.now(tz=timezone.utc))
        return DriftCheckResult(
            check_id=None,
            champion_version=champion_version,
            sample_count=0,
            overall_psi=0.0,
            max_feature_psi=0.0,
            triggered_retrain=False,
            triggered_run_id=None,
        )

    feature_stats = bundle.metadata.get("feature_stats") if isinstance(bundle.metadata, dict) else None
    if not isinstance(feature_stats, dict) or not feature_stats:
        db.upsert_runtime_state(last_drift_check_at=datetime.now(tz=timezone.utc))
        return DriftCheckResult(
            check_id=None,
            champion_version=champion_version,
            sample_count=0,
            overall_psi=0.0,
            max_feature_psi=0.0,
            triggered_retrain=False,
            triggered_run_id=None,
        )

    recent_rows, lookback_start, lookback_end = db.fetch_recent_model_features(
        model_version=champion_version,
        lookback_hours=settings.drift_lookback_hours,
        limit=settings.drift_sample_limit,
    )

    feature_rows: list[dict[str, Any]] = []
    psi_values: list[float] = []

    if len(recent_rows) >= settings.drift_min_samples:
        for feature, stat in feature_stats.items():
            if not isinstance(stat, dict):
                continue
            bins = stat.get("bins")
            expected_pct = stat.get("train_pct")
            if not isinstance(bins, list) or not isinstance(expected_pct, list):
                continue

            values = []
            for row in recent_rows:
                value = row.get(feature)
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(numeric):
                    values.append(numeric)

            if len(values) < settings.drift_min_samples:
                continue

            current_pct = _distribution(np.asarray(values, dtype=float), [float(x) for x in bins])
            if not current_pct or len(current_pct) != len(expected_pct):
                continue

            feature_psi = _psi([float(x) for x in expected_pct], current_pct)
            psi_values.append(feature_psi)
            feature_rows.append(
                {
                    "feature": feature,
                    "psi": feature_psi,
                    "sample_count": len(values),
                    "expected_pct": [float(x) for x in expected_pct],
                    "current_pct": current_pct,
                }
            )

    feature_rows.sort(key=lambda item: float(item.get("psi") or 0.0), reverse=True)

    if psi_values:
        overall_psi = float(np.mean(np.asarray(psi_values, dtype=float)))
        max_feature_psi = float(np.max(np.asarray(psi_values, dtype=float)))
    else:
        overall_psi = 0.0
        max_feature_psi = 0.0

    triggered = max_feature_psi > settings.drift_psi_threshold
    triggered_run_id: int | None = None

    if triggered and auto_retrain:
        from .trainer import run_train_once

        try:
            run = run_train_once(db)
            triggered_run_id = int(run.run_id)
            LOG.info("drift-triggered retrain run_id=%s version=%s promoted=%s", run.run_id, run.model_version, run.promoted)
        except Exception:
            LOG.exception("drift-triggered retrain failed")

    retrain_succeeded = triggered and auto_retrain and triggered_run_id is not None

    notes = "ok"
    if len(recent_rows) < settings.drift_min_samples:
        notes = "insufficient samples for PSI"
    elif triggered and triggered_run_id is None and auto_retrain:
        notes = "drift triggered but retrain failed"

    check_id = db.insert_drift_check(
        {
            "model_name": settings.model_name,
            "model_version": champion_version,
            "exchange": settings.default_exchange,
            "interval": settings.interval,
            "lookback_start": lookback_start,
            "lookback_end": lookback_end,
            "sample_count": len(recent_rows),
            "overall_psi": overall_psi,
            "max_feature_psi": max_feature_psi,
            "threshold": settings.drift_psi_threshold,
            "triggered_retrain": retrain_succeeded,
            "triggered_run_id": triggered_run_id,
            "drift_features": feature_rows[:20],
            "notes": notes,
        }
    )

    db.upsert_runtime_state(last_drift_check_at=datetime.now(tz=timezone.utc))

    return DriftCheckResult(
        check_id=check_id,
        champion_version=champion_version,
        sample_count=len(recent_rows),
        overall_psi=overall_psi,
        max_feature_psi=max_feature_psi,
        triggered_retrain=retrain_succeeded,
        triggered_run_id=triggered_run_id,
    )
