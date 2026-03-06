from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from src.config import settings
from src.db import get_pool
from src.response import api_response

router = APIRouter(tags=["ml"])

ALLOWED_WINDOWS = {"1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
ALLOWED_STATUS = {"pending", "passed", "review", "rejected", "unavailable"}


def _format_training_run(row: dict) -> dict:
    return {
        "id": row["id"],
        "model_name": row["model_name"],
        "model_version": row["model_version"],
        "train_start": row["train_start"].isoformat() if row.get("train_start") else None,
        "train_end": row["train_end"].isoformat() if row.get("train_end") else None,
        "val_start": row["val_start"].isoformat() if row.get("val_start") else None,
        "val_end": row["val_end"].isoformat() if row.get("val_end") else None,
        "test_start": row["test_start"].isoformat() if row.get("test_start") else None,
        "test_end": row["test_end"].isoformat() if row.get("test_end") else None,
        "sample_count": int(row.get("sample_count") or 0),
        "positive_ratio": float(row.get("positive_ratio") or 0.0),
        "threshold": float(row.get("threshold") or 0.0),
        "metrics": dict(row.get("metrics_json") or {}),
        "promoted": bool(row.get("promoted")),
        "notes": row.get("notes") or "",
        "run_type": row.get("run_type") or "train",
        "features_used": list(row.get("features_used") or []),
        "feature_importance": list(row.get("feature_importance") or []),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _event_to_candidate(row: dict) -> dict:
    event_ts = row.get("event_ts")
    detected_at = row.get("detected_at")

    ml_validation = None
    if row.get("model_version"):
        ml_validation = {
            "model_name": row.get("model_name"),
            "model_version": row.get("model_version"),
            "probability": float(row.get("probability") or 0.0),
            "threshold": float(row.get("threshold") or 0.0),
            "decision": row.get("decision") or "pending",
            "reason": row.get("reason") or "",
            "top_features": list(row.get("top_features") or []),
            "validated_at": row.get("validated_at").isoformat() if row.get("validated_at") else None,
        }

    return {
        "id": int(row["id"]),
        "exchange": row["exchange"],
        "symbol": row["symbol"],
        "interval": row["interval"],
        "rule_key": row["rule_key"],
        "direction": row["direction"],
        "event_ts": event_ts.isoformat() if isinstance(event_ts, datetime) else None,
        "detected_at": detected_at.isoformat() if isinstance(detected_at, datetime) else None,
        "score": float(row.get("score") or 0.0),
        "cooldown_seconds": int(row.get("cooldown_seconds") or 0),
        "detail": row.get("detail") or "",
        "payload": dict(row.get("payload") or {}),
        "ml_validation": ml_validation,
        "validation_status": (row.get("decision") or "pending"),
    }


@router.get("/ml/validation/summary")
def validation_summary(window: str = Query(default="1d")) -> dict:
    if window not in ALLOWED_WINDOWS:
        raise HTTPException(status_code=400, detail="window must be one of 1d/7d/30d")

    since = datetime.now(tz=timezone.utc) - ALLOWED_WINDOWS[window]
    sql = """
    SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE decision = 'passed') AS passed,
      COUNT(*) FILTER (WHERE decision = 'review') AS review,
      COUNT(*) FILTER (WHERE decision = 'rejected') AS rejected,
      COUNT(*) FILTER (WHERE decision = 'unavailable') AS unavailable,
      AVG(probability) FILTER (WHERE probability IS NOT NULL) AS avg_probability,
      MAX(validated_at) AS latest_validated_at
    FROM market_data_api.v_signal_ml_validation_v1
    WHERE validated_at >= %s
    """
    with get_pool().connection() as conn:
        row = conn.execute(sql, (since,)).fetchone()

    total = int(row["total"] or 0)
    passed = int(row["passed"] or 0)

    return api_response(
        {
            "window": window,
            "since": since.isoformat(),
            "total": total,
            "passed": passed,
            "review": int(row["review"] or 0),
            "rejected": int(row["rejected"] or 0),
            "unavailable": int(row["unavailable"] or 0),
            "pass_ratio": (passed / total) if total > 0 else 0.0,
            "avg_probability": float(row["avg_probability"] or 0.0),
            "latest_validated_at": row["latest_validated_at"].isoformat() if row.get("latest_validated_at") else None,
        }
    )


@router.get("/ml/validation/candidates")
def validation_candidates(
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    status: str | None = Query(default=None),
    cursor: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    if status and status not in ALLOWED_STATUS:
        raise HTTPException(status_code=400, detail="invalid status")

    sql = """
    SELECT
      e.id, e.exchange, e.symbol, e.interval, e.rule_key, e.direction,
      e.event_ts, e.detected_at, e.score, e.cooldown_seconds, e.detail, e.payload,
      mv.model_name, mv.model_version, mv.probability, mv.threshold, mv.decision,
      mv.reason, mv.top_features, mv.validated_at
    FROM market_data_api.v_signal_events_v1 e
    LEFT JOIN market_data_api.v_signal_ml_validation_latest_v1 mv ON mv.event_id = e.id
    WHERE e.exchange = %s
      AND e.rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
      AND (%s::text IS NULL OR e.symbol = %s)
      AND (%s::text IS NULL OR e.interval = %s)
      AND (%s::bigint IS NULL OR e.id < %s)
      AND (%s::text IS NULL OR COALESCE(mv.decision, 'pending') = %s)
    ORDER BY e.id DESC
    LIMIT %s
    """

    with get_pool().connection() as conn:
        rows = conn.execute(
            sql,
            (
                settings.default_exchange,
                symbol.upper() if symbol else None,
                symbol.upper() if symbol else None,
                interval.lower() if interval else None,
                interval.lower() if interval else None,
                cursor,
                cursor,
                status,
                status,
                limit,
            ),
        ).fetchall()

    data = [_event_to_candidate(dict(r)) for r in rows]
    next_cursor = data[-1]["id"] if data else None
    return api_response({"items": data, "next_cursor": next_cursor})


@router.get("/ml/validation/candidates/{event_id}")
def validation_candidate_detail(event_id: int) -> dict:
    sql = """
    SELECT
      e.id, e.exchange, e.symbol, e.interval, e.rule_key, e.direction,
      e.event_ts, e.detected_at, e.score, e.cooldown_seconds, e.detail, e.payload,
      mv.model_name, mv.model_version, mv.probability, mv.threshold, mv.decision,
      mv.reason, mv.top_features, mv.validated_at, mv.features, mv.label_horizon_bars,
      mv.label_due_at, mv.y_rsi_revert, mv.realized_return_bps
    FROM market_data_api.v_signal_events_v1 e
    LEFT JOIN market_data_api.v_signal_ml_validation_latest_v1 mv ON mv.event_id = e.id
    WHERE e.exchange = %s
      AND e.id = %s
      AND e.rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
    LIMIT 1
    """
    with get_pool().connection() as conn:
        row = conn.execute(sql, (settings.default_exchange, event_id)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="candidate not found")

    item = _event_to_candidate(dict(row))
    item["feature_snapshot"] = dict(row.get("features") or {})
    item["label_horizon_bars"] = int(row.get("label_horizon_bars") or 0)
    item["label_due_at"] = row["label_due_at"].isoformat() if row.get("label_due_at") else None
    item["y_rsi_revert"] = row.get("y_rsi_revert")
    item["realized_return_bps"] = float(row.get("realized_return_bps") or 0.0)

    return api_response(item)


@router.get("/ml/runtime")
def ml_runtime() -> dict:
    runtime_sql = """
    SELECT champion_version, last_processed_event_id, last_train_run_id, last_train_at,
           last_train_attempt_at, last_train_status, last_train_error,
           last_train_sample_count, last_train_positive_ratio, last_drift_check_at
    FROM market_data_api.v_signal_ml_runtime_state_v1
    WHERE id = 1
    """
    latest_total_sql = """
    SELECT COALESCE(MAX(id), 0) AS max_id
    FROM market_data_api.v_signal_events_v1
    WHERE exchange = %s
      AND rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
    """
    latest_scoped_sql = """
    SELECT COALESCE(MAX(id), 0) AS max_id
    FROM market_data_api.v_signal_events_v1
    WHERE exchange = %s
      AND interval = %s
      AND rule_key IN ('RSI_OVERBOUGHT', 'RSI_OVERSOLD')
    """
    with get_pool().connection() as conn:
        runtime = conn.execute(runtime_sql).fetchone()
        latest_total = conn.execute(latest_total_sql, (settings.default_exchange,)).fetchone()
        latest_scoped = conn.execute(latest_scoped_sql, (settings.default_exchange, settings.ml_interval)).fetchone()

    if not runtime:
        return api_response(
            {
                "champion_version": None,
                "last_processed_event_id": 0,
                "last_train_run_id": None,
                "last_train_at": None,
                "last_train_attempt_at": None,
                "last_train_status": "never",
                "last_train_error": None,
                "last_train_sample_count": 0,
                "last_train_positive_ratio": 0.0,
                "last_drift_check_at": None,
                "queue_lag": 0,
                "queue_lag_total": 0,
                "queue_lag_scoped": 0,
                "runtime_interval": settings.ml_interval,
            }
        )

    latest_total_id = int((latest_total or {}).get("max_id") or 0)
    latest_scoped_id = int((latest_scoped or {}).get("max_id") or 0)
    last_processed = int(runtime.get("last_processed_event_id") or 0)
    queue_lag_total = max(0, latest_total_id - last_processed)
    queue_lag_scoped = max(0, latest_scoped_id - last_processed)
    return api_response(
        {
            "champion_version": runtime.get("champion_version"),
            "last_processed_event_id": last_processed,
            "last_train_run_id": runtime.get("last_train_run_id"),
            "last_train_at": runtime["last_train_at"].isoformat() if runtime.get("last_train_at") else None,
            "last_train_attempt_at": runtime["last_train_attempt_at"].isoformat() if runtime.get("last_train_attempt_at") else None,
            "last_train_status": runtime.get("last_train_status") or "never",
            "last_train_error": runtime.get("last_train_error") or None,
            "last_train_sample_count": int(runtime.get("last_train_sample_count") or 0),
            "last_train_positive_ratio": float(runtime.get("last_train_positive_ratio") or 0.0),
            "last_drift_check_at": runtime["last_drift_check_at"].isoformat() if runtime.get("last_drift_check_at") else None,
            "queue_lag": queue_lag_total,
            "queue_lag_total": queue_lag_total,
            "queue_lag_scoped": queue_lag_scoped,
            "runtime_interval": settings.ml_interval,
        }
    )


@router.get("/ml/training/runs")
def training_runs(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    sql = """
    SELECT id, model_name, model_version, train_start, train_end, val_start, val_end,
           test_start, test_end, sample_count, positive_ratio, threshold,
           metrics_json, promoted, notes, created_at, run_type,
           features_used, feature_importance
    FROM market_data_api.v_signal_ml_training_runs_v1
    ORDER BY created_at DESC
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return api_response([_format_training_run(dict(r)) for r in rows])


@router.get("/ml/training/runs/{run_id}")
def training_run_detail(run_id: int) -> dict:
    sql = """
    SELECT id, model_name, model_version, train_start, train_end, val_start, val_end,
           test_start, test_end, sample_count, positive_ratio, threshold,
           metrics_json, promoted, notes, created_at, run_type,
           features_used, feature_importance
    FROM market_data_api.v_signal_ml_training_runs_v1
    WHERE id = %s
    LIMIT 1
    """
    with get_pool().connection() as conn:
        row = conn.execute(sql, (run_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="training run not found")
    return api_response(_format_training_run(dict(row)))


@router.get("/ml/drift/latest")
def drift_latest(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    sql = """
    SELECT id, model_name, model_version, exchange, interval,
           lookback_start, lookback_end, sample_count, overall_psi,
           max_feature_psi, threshold, triggered_retrain, triggered_run_id,
           drift_features, notes, created_at
    FROM market_data_api.v_signal_ml_drift_checks_v1
    ORDER BY created_at DESC
    LIMIT %s
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    data = []
    for row in rows:
        data.append(
            {
                "id": row["id"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "exchange": row["exchange"],
                "interval": row["interval"],
                "lookback_start": row["lookback_start"].isoformat() if row.get("lookback_start") else None,
                "lookback_end": row["lookback_end"].isoformat() if row.get("lookback_end") else None,
                "sample_count": int(row.get("sample_count") or 0),
                "overall_psi": float(row.get("overall_psi") or 0.0),
                "max_feature_psi": float(row.get("max_feature_psi") or 0.0),
                "threshold": float(row.get("threshold") or 0.0),
                "triggered_retrain": bool(row.get("triggered_retrain")),
                "triggered_run_id": row.get("triggered_run_id"),
                "drift_features": list(row.get("drift_features") or []),
                "notes": row.get("notes") or "",
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
        )
    return api_response(data)


@router.get("/ml/validation/metrics")
def validation_metrics(window: str = Query(default="7d")) -> dict:
    if window not in ALLOWED_WINDOWS:
        raise HTTPException(status_code=400, detail="window must be one of 1d/7d/30d")

    since = datetime.now(tz=timezone.utc) - ALLOWED_WINDOWS[window]

    run_sql = """
    SELECT id, model_name, model_version, threshold, metrics_json, promoted, created_at
    FROM market_data_api.v_signal_ml_training_runs_v1
    WHERE promoted = true
    ORDER BY created_at DESC
    LIMIT 1
    """
    summary_sql = """
    SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE decision = 'passed') AS passed,
      COUNT(*) FILTER (WHERE decision = 'review') AS review,
      COUNT(*) FILTER (WHERE decision = 'rejected') AS rejected,
      AVG(probability) FILTER (WHERE probability IS NOT NULL) AS avg_probability
    FROM market_data_api.v_signal_ml_validation_v1
    WHERE validated_at >= %s
    """

    with get_pool().connection() as conn:
        run = conn.execute(run_sql).fetchone()
        summary = conn.execute(summary_sql, (since,)).fetchone()

    total = int(summary["total"] or 0)
    passed = int(summary["passed"] or 0)

    return api_response(
        {
            "window": window,
            "since": since.isoformat(),
            "current_model": {
                "id": int(run["id"]) if run else None,
                "model_name": run["model_name"] if run else None,
                "model_version": run["model_version"] if run else None,
                "threshold": float(run["threshold"] or 0.0) if run else None,
                "metrics": dict(run["metrics_json"] or {}) if run else {},
                "promoted": bool(run["promoted"]) if run else False,
                "created_at": run["created_at"].isoformat() if run and run.get("created_at") else None,
            },
            "live_stats": {
                "total": total,
                "passed": passed,
                "review": int(summary["review"] or 0),
                "rejected": int(summary["rejected"] or 0),
                "pass_ratio": (passed / total) if total > 0 else 0.0,
                "avg_probability": float(summary["avg_probability"] or 0.0),
            },
        }
    )
