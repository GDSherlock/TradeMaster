from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, fbeta_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import settings
from .dataset import DatasetBuildStats, build_training_dataset_with_stats
from .db import Database
from .registry import make_model_version, save_model_bundle

PSI_BIN_COUNT = 5
LOG = logging.getLogger(__name__)


@dataclass
class TrainResult:
    run_id: int
    model_version: str
    promoted: bool
    threshold: float
    sample_count: int
    val_precision: float
    test_precision: float


def _label_counts(values: np.ndarray) -> dict[int, int]:
    unique, counts = np.unique(values.astype(int), return_counts=True)
    return {int(label): int(count) for label, count in zip(unique, counts)}


def _split_positive_ratio(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    return float(frame["y"].astype(int).mean())


def _require_binary_labels(name: str, values: np.ndarray) -> None:
    counts = _label_counts(values)
    if len(counts) < 2:
        raise RuntimeError(f"single-class {name}: labels={counts}")


def _build_base_estimator() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=800, class_weight="balanced", random_state=42)),
        ]
    )


def _safe_metric(fn, y_true: np.ndarray, y_pred: np.ndarray | None = None, y_score: np.ndarray | None = None) -> float:
    try:
        if y_score is not None:
            return float(fn(y_true, y_score))
        if y_pred is not None:
            return float(fn(y_true, y_pred))
    except Exception:
        return 0.0
    return 0.0


def _calc_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> dict[str, float]:
    y_hat = (y_score >= threshold).astype(int)
    coverage = float(np.mean(y_hat)) if y_hat.size > 0 else 0.0

    metrics = {
        "precision": _safe_metric(precision_score, y_true, y_pred=y_hat),
        "recall": _safe_metric(recall_score, y_true, y_pred=y_hat),
        "f1": _safe_metric(f1_score, y_true, y_pred=y_hat),
        "pr_auc": _safe_metric(average_precision_score, y_true, y_score=y_score),
        "brier": _safe_metric(brier_score_loss, y_true, y_score=y_score),
        "coverage": coverage,
    }
    return metrics


def _choose_threshold(y_true: np.ndarray, y_score: np.ndarray) -> float:
    best_t = settings.model_threshold_default
    best_score = -1.0
    for t in np.arange(0.30, 0.81, 0.01):
        y_hat = (y_score >= t).astype(int)
        try:
            score = float(fbeta_score(y_true, y_hat, beta=0.5))
        except Exception:
            score = -1.0
        if score > best_score:
            best_score = score
            best_t = float(t)
    return best_t


def _resolve_linear_classifier(model: Any) -> Any | None:
    if hasattr(model, "named_steps"):
        return model.named_steps.get("clf")

    calibrated = getattr(model, "calibrated_classifiers_", None)
    if calibrated:
        for wrapper in calibrated:
            estimator = getattr(wrapper, "estimator", None)
            if estimator is not None and hasattr(estimator, "named_steps"):
                clf = estimator.named_steps.get("clf")
                if clf is not None:
                    return clf
    return None


def _compute_feature_importance(model: Any, feature_names: list[str], top_k: int = 10) -> list[dict[str, float]]:
    clf = _resolve_linear_classifier(model)
    if clf is None or not hasattr(clf, "coef_"):
        return []

    coef = np.ravel(np.asarray(clf.coef_, dtype=float))
    if coef.size != len(feature_names):
        return []

    rows: list[dict[str, float]] = []
    for idx, name in enumerate(feature_names):
        c = float(coef[idx])
        rows.append({"name": name, "coef": c, "abs_coef": abs(c)})

    rows.sort(key=lambda item: float(item["abs_coef"]), reverse=True)
    return rows[:top_k]


def _feature_bins(values: np.ndarray, bins: int = PSI_BIN_COUNT) -> list[float]:
    quantiles = np.linspace(0.0, 1.0, bins + 1)
    edges = np.quantile(values, quantiles).astype(float)
    unique_edges = np.unique(edges)
    if unique_edges.size < 3:
        min_v = float(np.min(values))
        max_v = float(np.max(values))
        if min_v == max_v:
            max_v = min_v + 1.0
        unique_edges = np.array([min_v, (min_v + max_v) / 2.0, max_v], dtype=float)
    return [float(x) for x in unique_edges.tolist()]


def _bin_distribution(values: np.ndarray, edges: list[float]) -> list[float]:
    if len(edges) < 2:
        return [1.0]
    hist, _ = np.histogram(values, bins=np.asarray(edges, dtype=float))
    total = int(np.sum(hist))
    if total <= 0:
        return [0.0 for _ in hist]
    return [float(v / total) for v in hist.tolist()]


def _compute_feature_stats(train_df: pd.DataFrame, feature_names: list[str]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for feature in feature_names:
        arr = train_df[feature].astype(float).to_numpy()
        arr = arr[np.isfinite(arr)]
        if arr.size < 10:
            continue
        edges = _feature_bins(arr, bins=PSI_BIN_COUNT)
        stats[feature] = {
            "bins": edges,
            "train_pct": _bin_distribution(arr, edges),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
        }
    return stats


def _split_windows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, datetime]]:
    max_ts = df["event_ts"].max()
    test_start = max_ts - timedelta(days=settings.test_days)
    val_start = test_start - timedelta(days=settings.val_days)

    train_df = df[df["event_ts"] < val_start]
    val_df = df[(df["event_ts"] >= val_start) & (df["event_ts"] < test_start)]
    test_df = df[df["event_ts"] >= test_start]

    windows = {
        "train_start": train_df["event_ts"].min(),
        "train_end": train_df["event_ts"].max(),
        "val_start": val_df["event_ts"].min(),
        "val_end": val_df["event_ts"].max(),
        "test_start": test_df["event_ts"].min(),
        "test_end": test_df["event_ts"].max(),
    }
    return train_df, val_df, test_df, windows


def _promote_decision(db: Database, candidate_metrics: dict[str, float]) -> bool:
    baseline = db.fetch_latest_promoted_run(settings.model_name)
    if not baseline:
        return True

    baseline_metrics = dict(baseline.get("metrics_json") or {})
    baseline_test = dict(baseline_metrics.get("test") or {})

    precision_gain = float(candidate_metrics.get("precision", 0.0) - float(baseline_test.get("precision", 0.0)))
    pr_auc_new = float(candidate_metrics.get("pr_auc", 0.0))
    pr_auc_old = float(baseline_test.get("pr_auc", 0.0))
    brier_new = float(candidate_metrics.get("brier", 1.0))
    brier_old = float(baseline_test.get("brier", 1.0))
    coverage = float(candidate_metrics.get("coverage", 0.0))

    if precision_gain < settings.promote_min_precision_gain:
        return False
    if pr_auc_new < pr_auc_old:
        return False
    if (brier_new - brier_old) > settings.promote_max_brier_degrade:
        return False
    if not (settings.coverage_min <= coverage <= settings.coverage_max):
        return False
    return True


def run_train_once(db: Database) -> TrainResult:
    attempt_at = datetime.now(tz=timezone.utc)
    stats = DatasetBuildStats()
    db.upsert_runtime_state(
        last_train_attempt_at=attempt_at,
        last_train_status="running",
        last_train_error="",
        last_train_sample_count=0,
        last_train_positive_ratio=0.0,
    )

    try:
        samples, stats = build_training_dataset_with_stats(db)
        LOG.info(
            "training dataset built interval=%s lookback_days=%s events=%s samples=%s positive=%s negative=%s "
            "positive_ratio=%.4f dropped_invalid=%s dropped_missing_indicator=%s dropped_recent=%s dropped_future=%s",
            settings.interval,
            settings.lookback_days,
            stats.total_events,
            stats.built_samples,
            stats.positive_labels,
            stats.negative_labels,
            stats.positive_ratio,
            stats.dropped_invalid_event,
            stats.dropped_missing_indicator_snapshot,
            stats.dropped_insufficient_recent_bars,
            stats.dropped_insufficient_future_bars,
        )
        db.upsert_runtime_state(
            last_train_attempt_at=attempt_at,
            last_train_status="running",
            last_train_error="",
            last_train_sample_count=stats.built_samples,
            last_train_positive_ratio=stats.positive_ratio,
        )

        if len(samples) < settings.min_samples:
            raise RuntimeError(f"insufficient samples: {len(samples)} < {settings.min_samples}")

        rows: list[dict[str, Any]] = []
        for s in samples:
            row = {
                "event_id": s.event_id,
                "event_ts": s.event_ts,
                "y": s.y_pass,
            }
            row.update(s.features)
            rows.append(row)

        df = pd.DataFrame(rows)
        df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
        df = df.sort_values("event_ts").reset_index(drop=True)
        y_all = df["y"].astype(int).to_numpy()
        _require_binary_labels("dataset", y_all)

        train_df, val_df, test_df, windows = _split_windows(df)
        LOG.info(
            "training split built train=%s val=%s test=%s train_pos=%.4f val_pos=%.4f test_pos=%.4f "
            "train_labels=%s val_labels=%s test_labels=%s",
            len(train_df),
            len(val_df),
            len(test_df),
            _split_positive_ratio(train_df),
            _split_positive_ratio(val_df),
            _split_positive_ratio(test_df),
            _label_counts(train_df["y"].astype(int).to_numpy()) if not train_df.empty else {},
            _label_counts(val_df["y"].astype(int).to_numpy()) if not val_df.empty else {},
            _label_counts(test_df["y"].astype(int).to_numpy()) if not test_df.empty else {},
        )
        if train_df.empty or val_df.empty or test_df.empty:
            raise RuntimeError("insufficient split size for train/val/test")

        feature_names = [c for c in df.columns if c not in {"event_id", "event_ts", "y"}]
        x_train = train_df[feature_names]
        y_train = train_df["y"].astype(int).to_numpy()
        x_val = val_df[feature_names]
        y_val = val_df["y"].astype(int).to_numpy()
        x_test = test_df[feature_names]
        y_test = test_df["y"].astype(int).to_numpy()
        _require_binary_labels("train split", y_train)
        _require_binary_labels("val split", y_val)
        _require_binary_labels("test split", y_test)

        estimator = _build_base_estimator()
        class_counts = np.bincount(y_train, minlength=2)

        if int(class_counts.min()) >= 3:
            model = CalibratedClassifierCV(estimator=estimator, method="isotonic", cv=3)
        else:
            model = estimator

        model.fit(x_train, y_train)

        y_val_score = model.predict_proba(x_val)[:, 1]
        threshold = _choose_threshold(y_val, y_val_score)

        val_metrics = _calc_metrics(y_val, y_val_score, threshold)
        y_test_score = model.predict_proba(x_test)[:, 1]
        test_metrics = _calc_metrics(y_test, y_test_score, threshold)
        feature_importance = _compute_feature_importance(model, feature_names, top_k=12)
        feature_stats = _compute_feature_stats(train_df, feature_names)

        promoted = _promote_decision(db, test_metrics)

        model_version = make_model_version(settings.model_name)
        metadata = {
            "model_name": settings.model_name,
            "model_version": model_version,
            "threshold": threshold,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "feature_count": len(feature_names),
            "features_used": feature_names,
            "coef_topk": feature_importance,
            "feature_stats": feature_stats,
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
        }

        save_model_bundle(
            model_version=model_version,
            model=model,
            metadata=metadata,
            feature_names=feature_names,
        )

        metrics_json = {
            "val": val_metrics,
            "test": test_metrics,
        }

        run_id = db.insert_training_run(
            {
                "model_name": settings.model_name,
                "model_version": model_version,
                "train_start": windows["train_start"],
                "train_end": windows["train_end"],
                "val_start": windows["val_start"],
                "val_end": windows["val_end"],
                "test_start": windows["test_start"],
                "test_end": windows["test_end"],
                "sample_count": int(len(df)),
                "positive_ratio": float(df["y"].mean()),
                "threshold": float(threshold),
                "metrics_json": metrics_json,
                "promoted": promoted,
                "notes": "shadow-mode training",
                "run_type": "train",
                "features_used": feature_names,
                "feature_importance": feature_importance,
            }
        )

        db.upsert_runtime_state(
            champion_version=model_version if promoted else None,
            last_train_run_id=run_id,
            last_train_at=datetime.now(tz=timezone.utc),
            last_train_attempt_at=attempt_at,
            last_train_status="succeeded",
            last_train_error="",
            last_train_sample_count=int(len(df)),
            last_train_positive_ratio=float(df["y"].mean()),
        )

        if promoted and settings.revalidate_on_promotion:
            from .worker import ValidationWorker

            try:
                revalidated = ValidationWorker(db).revalidate_recent_candidates()
                LOG.info(
                    "promotion revalidation complete run_id=%s version=%s processed=%s",
                    run_id,
                    model_version,
                    revalidated,
                )
            except Exception:
                LOG.exception("promotion revalidation failed run_id=%s version=%s", run_id, model_version)

        return TrainResult(
            run_id=run_id,
            model_version=model_version,
            promoted=promoted,
            threshold=threshold,
            sample_count=len(df),
            val_precision=float(val_metrics.get("precision", 0.0)),
            test_precision=float(test_metrics.get("precision", 0.0)),
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        db.upsert_runtime_state(
            last_train_attempt_at=attempt_at,
            last_train_status="failed",
            last_train_error=message[:500],
            last_train_sample_count=stats.built_samples,
            last_train_positive_ratio=stats.positive_ratio,
        )
        raise
