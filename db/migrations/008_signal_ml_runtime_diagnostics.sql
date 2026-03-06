ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_train_attempt_at TIMESTAMPTZ;

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_train_status TEXT NOT NULL DEFAULT 'never';

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_train_error TEXT NOT NULL DEFAULT '';

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_train_sample_count INT NOT NULL DEFAULT 0;

ALTER TABLE market_data.signal_ml_runtime_state
    ADD COLUMN IF NOT EXISTS last_train_positive_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.0;

CREATE OR REPLACE VIEW market_data_api.v_signal_ml_runtime_state_v1 AS
SELECT
    id,
    champion_version,
    last_processed_event_id,
    last_train_run_id,
    last_train_at,
    last_train_attempt_at,
    last_train_status,
    last_train_error,
    last_train_sample_count,
    last_train_positive_ratio,
    last_drift_check_at,
    updated_at
FROM market_data.signal_ml_runtime_state;
