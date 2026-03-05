CREATE SCHEMA IF NOT EXISTS market_data;

CREATE TABLE IF NOT EXISTS market_data.signal_ml_validation (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES market_data.signal_events (id) ON DELETE CASCADE,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    direction TEXT NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    probability DOUBLE PRECISION,
    threshold DOUBLE PRECISION,
    decision TEXT NOT NULL,
    reason TEXT,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    top_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    validated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latency_ms INT,
    label_horizon_bars INT,
    label_due_at TIMESTAMPTZ,
    y_rsi_revert SMALLINT,
    realized_return_bps DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_signal_ml_decision CHECK (decision IN ('passed', 'review', 'rejected', 'pending', 'unavailable')),
    CONSTRAINT uq_signal_ml_event_model UNIQUE (event_id, model_version)
);

CREATE INDEX IF NOT EXISTS idx_signal_ml_validation_event_id
    ON market_data.signal_ml_validation (event_id DESC);

CREATE INDEX IF NOT EXISTS idx_signal_ml_validation_validated_at
    ON market_data.signal_ml_validation (validated_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_ml_validation_symbol_interval
    ON market_data.signal_ml_validation (symbol, interval, validated_at DESC);

CREATE TABLE IF NOT EXISTS market_data.signal_ml_training_runs (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    train_start TIMESTAMPTZ,
    train_end TIMESTAMPTZ,
    val_start TIMESTAMPTZ,
    val_end TIMESTAMPTZ,
    test_start TIMESTAMPTZ,
    test_end TIMESTAMPTZ,
    sample_count INT NOT NULL DEFAULT 0,
    positive_ratio DOUBLE PRECISION,
    threshold DOUBLE PRECISION,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    promoted BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_signal_ml_training_model_version UNIQUE (model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_signal_ml_training_runs_created_at
    ON market_data.signal_ml_training_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS market_data.signal_ml_runtime_state (
    id INT PRIMARY KEY,
    champion_version TEXT,
    last_processed_event_id BIGINT NOT NULL DEFAULT 0,
    last_train_run_id BIGINT,
    last_train_at TIMESTAMPTZ,
    last_drift_check_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_signal_ml_runtime_singleton CHECK (id = 1)
);

INSERT INTO market_data.signal_ml_runtime_state (id, last_processed_event_id)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
