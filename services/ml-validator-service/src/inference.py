from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import settings
from .registry import ModelBundle


def _coerce_feature_vector(feature_names: list[str], feature_map: dict[str, float]) -> pd.DataFrame:
    row = {name: float(feature_map.get(name, 0.0)) for name in feature_names}
    return pd.DataFrame([row])


def _top_feature_proxy(feature_map: dict[str, float], top_n: int) -> list[dict[str, float]]:
    items = sorted(feature_map.items(), key=lambda kv: abs(float(kv[1])), reverse=True)
    return [{"name": k, "value": float(v)} for k, v in items[:top_n]]


def predict_validation(
    bundle: ModelBundle | None,
    feature_map: dict[str, float],
) -> dict[str, Any]:
    if bundle is None:
        return {
            "model_name": settings.model_name,
            "model_version": "unavailable",
            "probability": 0.0,
            "threshold": settings.model_threshold_default,
            "decision": "unavailable",
            "reason": "model unavailable",
            "top_features": _top_feature_proxy(feature_map, settings.top_feature_count),
        }

    features = _coerce_feature_vector(bundle.feature_names, feature_map)
    proba = float(bundle.model.predict_proba(features)[:, 1][0])

    threshold = float(bundle.metadata.get("threshold", settings.model_threshold_default))
    review_threshold = max(0.0, threshold - 0.10)

    if proba >= threshold:
        decision = "passed"
        reason = "probability above threshold"
    elif proba >= review_threshold:
        decision = "review"
        reason = "probability near threshold"
    else:
        decision = "rejected"
        reason = "probability below threshold"

    if not np.isfinite(proba):
        proba = 0.0
        decision = "unavailable"
        reason = "invalid model output"

    return {
        "model_name": settings.model_name,
        "model_version": bundle.model_version,
        "probability": proba,
        "threshold": threshold,
        "decision": decision,
        "reason": reason,
        "top_features": _top_feature_proxy(feature_map, settings.top_feature_count),
    }
