CREATE SCHEMA IF NOT EXISTS market_data_api;

DROP VIEW IF EXISTS market_data_api.v_candles_1m_v1;
CREATE VIEW market_data_api.v_candles_1m_v1 AS
SELECT
    exchange,
    symbol,
    bucket_ts,
    open,
    high,
    low,
    close,
    volume,
    quote_volume,
    trade_count,
    is_closed,
    source,
    ingested_at,
    updated_at
FROM market_data.candles_1m;

DROP VIEW IF EXISTS market_data_api.v_indicator_values_v1;
CREATE VIEW market_data_api.v_indicator_values_v1 AS
SELECT
    exchange,
    symbol,
    interval,
    indicator,
    ts,
    payload,
    stale,
    source,
    updated_at
FROM market_data.indicator_values;

DROP VIEW IF EXISTS market_data_api.v_signal_events_v1;
CREATE VIEW market_data_api.v_signal_events_v1 AS
SELECT
    id,
    exchange,
    symbol,
    interval,
    rule_key,
    signal_type,
    direction,
    event_ts,
    detected_at,
    price,
    score,
    cooldown_seconds,
    detail,
    payload
FROM market_data.signal_events;

DROP VIEW IF EXISTS market_data_api.v_signal_rule_configs_v1;
CREATE VIEW market_data_api.v_signal_rule_configs_v1 AS
SELECT
    rule_key,
    enabled,
    priority,
    cooldown_seconds,
    params,
    scope_symbols,
    scope_intervals,
    updated_at
FROM market_data.signal_rule_configs;

DROP VIEW IF EXISTS market_data_api.v_signal_ml_validation_v1;
CREATE VIEW market_data_api.v_signal_ml_validation_v1 AS
SELECT
    id,
    event_id,
    exchange,
    symbol,
    interval,
    rule_key,
    direction,
    event_ts,
    model_name,
    model_version,
    probability,
    threshold,
    decision,
    reason,
    features,
    top_features,
    validated_at,
    latency_ms,
    label_horizon_bars,
    label_due_at,
    y_rsi_revert,
    realized_return_bps,
    created_at,
    updated_at
FROM market_data.signal_ml_validation;

DROP VIEW IF EXISTS market_data_api.v_signal_ml_validation_latest_v1;
CREATE VIEW market_data_api.v_signal_ml_validation_latest_v1 AS
SELECT DISTINCT ON (event_id)
    id,
    event_id,
    exchange,
    symbol,
    interval,
    rule_key,
    direction,
    event_ts,
    model_name,
    model_version,
    probability,
    threshold,
    decision,
    reason,
    features,
    top_features,
    validated_at,
    latency_ms,
    label_horizon_bars,
    label_due_at,
    y_rsi_revert,
    realized_return_bps,
    created_at,
    updated_at
FROM market_data.signal_ml_validation
ORDER BY
    event_id,
    validated_at DESC,
    CASE WHEN model_version IN ('', 'unavailable') THEN 1 ELSE 0 END,
    id DESC;

DROP VIEW IF EXISTS market_data_api.v_signal_ml_training_runs_v1;
CREATE VIEW market_data_api.v_signal_ml_training_runs_v1 AS
SELECT
    id,
    model_name,
    model_version,
    train_start,
    train_end,
    val_start,
    val_end,
    test_start,
    test_end,
    sample_count,
    positive_ratio,
    threshold,
    metrics_json,
    promoted,
    notes,
    created_at,
    run_type,
    features_used,
    feature_importance
FROM market_data.signal_ml_training_runs;

DROP VIEW IF EXISTS market_data_api.v_signal_ml_runtime_state_v1;
CREATE VIEW market_data_api.v_signal_ml_runtime_state_v1 AS
SELECT
    id,
    champion_version,
    last_processed_event_id,
    last_train_run_id,
    last_train_at,
    last_drift_check_at,
    updated_at
FROM market_data.signal_ml_runtime_state;

DROP VIEW IF EXISTS market_data_api.v_signal_ml_drift_checks_v1;
CREATE VIEW market_data_api.v_signal_ml_drift_checks_v1 AS
SELECT
    id,
    model_name,
    model_version,
    exchange,
    interval,
    lookback_start,
    lookback_end,
    sample_count,
    overall_psi,
    max_feature_psi,
    threshold,
    triggered_retrain,
    triggered_run_id,
    drift_features,
    notes,
    created_at
FROM market_data.signal_ml_drift_checks;
