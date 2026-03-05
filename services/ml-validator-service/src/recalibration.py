from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from .config import settings
from .dataset import build_training_dataset
from .db import Database
from .registry import load_champion_bundle, update_model_metadata
from .trainer import _calc_metrics, _choose_threshold


@dataclass
class RecalibrationResult:
    recalibration_id: int
    champion_version: str
    sample_count: int
    old_threshold: float
    new_threshold: float
    promoted: bool


def _build_frame(samples: list[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sample in samples:
        row = {
            "event_id": sample.event_id,
            "event_ts": sample.event_ts,
            "y": sample.y_pass,
        }
        row.update(sample.features)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
    return df.sort_values("event_ts").reset_index(drop=True)


def run_recalibration_once(db: Database) -> RecalibrationResult:
    runtime = db.fetch_runtime_state()
    champion_version = runtime.get("champion_version")
    if not champion_version:
        raise RuntimeError("cannot recalibrate without champion model")

    bundle = load_champion_bundle(champion_version)
    if bundle is None:
        raise RuntimeError(f"champion model unavailable: {champion_version}")

    samples = build_training_dataset(db)
    if not samples:
        raise RuntimeError("no labeled samples available for recalibration")

    df = _build_frame(samples)

    lookback_start = datetime.now(tz=timezone.utc) - timedelta(days=max(7, settings.recalibrate_lookback_days))
    df = df[df["event_ts"] >= lookback_start]
    if df.empty:
        raise RuntimeError("insufficient recalibration samples in lookback window")

    feature_names = [name for name in bundle.feature_names if name in df.columns]
    if not feature_names:
        raise RuntimeError("champion feature list not found in recalibration dataset")

    x = df[feature_names]
    y = df["y"].astype(int).to_numpy()

    if y.size < settings.min_samples:
        raise RuntimeError(f"insufficient recalibration samples: {y.size} < {settings.min_samples}")

    score = bundle.model.predict_proba(x)[:, 1]

    old_threshold = float(bundle.metadata.get("threshold", settings.model_threshold_default))
    new_threshold = _choose_threshold(y, score)

    metrics_before = _calc_metrics(y, score, old_threshold)
    metrics_after = _calc_metrics(y, score, new_threshold)

    promoted = bool(
        metrics_after.get("coverage", 0.0) >= settings.coverage_min
        and metrics_after.get("coverage", 0.0) <= settings.coverage_max
        and metrics_after.get("precision", 0.0) >= metrics_before.get("precision", 0.0) - 0.01
        and metrics_after.get("f1", 0.0) >= metrics_before.get("f1", 0.0) - 0.01
    )

    if promoted:
        update_model_metadata(
            champion_version,
            {
                "threshold": float(new_threshold),
                "threshold_updated_at": datetime.now(tz=timezone.utc).isoformat(),
                "threshold_source": "weekly_recalibration",
            },
        )

    recalibration_id = db.insert_recalibration_run(
        {
            "model_name": settings.model_name,
            "model_version": champion_version,
            "old_threshold": old_threshold,
            "new_threshold": float(new_threshold),
            "lookback_start": df["event_ts"].min(),
            "lookback_end": df["event_ts"].max(),
            "sample_count": int(y.size),
            "metrics_json": {
                "before": metrics_before,
                "after": metrics_after,
                "threshold_delta": float(new_threshold - old_threshold),
            },
            "promoted": promoted,
            "notes": "weekly threshold recalibration",
        }
    )

    return RecalibrationResult(
        recalibration_id=recalibration_id,
        champion_version=champion_version,
        sample_count=int(y.size),
        old_threshold=old_threshold,
        new_threshold=float(new_threshold),
        promoted=promoted,
    )
