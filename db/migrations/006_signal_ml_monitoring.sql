CREATE TABLE IF NOT EXISTS market_data.signal_ml_drift_checks (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    exchange TEXT NOT NULL,
    interval TEXT NOT NULL,
    lookback_start TIMESTAMPTZ,
    lookback_end TIMESTAMPTZ,
    sample_count INT NOT NULL DEFAULT 0,
    overall_psi DOUBLE PRECISION NOT NULL DEFAULT 0,
    max_feature_psi DOUBLE PRECISION NOT NULL DEFAULT 0,
    threshold DOUBLE PRECISION NOT NULL DEFAULT 0.2,
    triggered_retrain BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_run_id BIGINT,
    drift_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_ml_drift_checks_created_at
    ON market_data.signal_ml_drift_checks (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_ml_drift_checks_model_version
    ON market_data.signal_ml_drift_checks (model_version, created_at DESC);

CREATE TABLE IF NOT EXISTS market_data.signal_ml_recalibration_runs (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    old_threshold DOUBLE PRECISION,
    new_threshold DOUBLE PRECISION,
    lookback_start TIMESTAMPTZ,
    lookback_end TIMESTAMPTZ,
    sample_count INT NOT NULL DEFAULT 0,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    promoted BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_ml_recalibration_runs_created_at
    ON market_data.signal_ml_recalibration_runs (created_at DESC);

ALTER TABLE market_data.signal_ml_training_runs
    ADD COLUMN IF NOT EXISTS run_type TEXT NOT NULL DEFAULT 'train';

ALTER TABLE market_data.signal_ml_training_runs
    ADD COLUMN IF NOT EXISTS features_used JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE market_data.signal_ml_training_runs
    ADD COLUMN IF NOT EXISTS feature_importance JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_signal_ml_training_runs_run_type
    ON market_data.signal_ml_training_runs (run_type, created_at DESC);
