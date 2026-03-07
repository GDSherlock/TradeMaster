CREATE OR REPLACE VIEW market_data_api.v_signal_ml_validation_latest_v1 AS
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
