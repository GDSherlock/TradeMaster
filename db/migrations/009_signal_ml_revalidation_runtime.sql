ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_revalidate_at TIMESTAMPTZ;

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_revalidate_status TEXT NOT NULL DEFAULT 'never';

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_revalidate_error TEXT NOT NULL DEFAULT '';

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_revalidate_processed_count INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_signal_ml_validation_event_validated_latest
    ON market_data.signal_ml_validation (event_id, validated_at DESC, id DESC);

DROP VIEW IF EXISTS market_data_api.v_signal_ml_runtime_state_v1;

CREATE VIEW market_data_api.v_signal_ml_runtime_state_v1 AS
SELECT
    id,
    champion_version,
    last_processed_event_id,
    last_train_run_id,
    last_train_at,
    last_drift_check_at,
    updated_at,
    last_train_attempt_at,
    last_train_status,
    last_train_error,
    last_train_sample_count,
    last_train_positive_ratio,
    last_revalidate_at,
    last_revalidate_status,
    last_revalidate_error,
    last_revalidate_processed_count
FROM market_data.signal_ml_runtime_state;
