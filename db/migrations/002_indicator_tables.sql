CREATE SCHEMA IF NOT EXISTS market_data;

CREATE TABLE IF NOT EXISTS market_data.indicator_values (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    indicator TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL DEFAULT 'indicator_engine',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (exchange, symbol, interval, indicator, ts)
);

CREATE INDEX IF NOT EXISTS idx_indicator_values_symbol_interval_ts
    ON market_data.indicator_values (symbol, interval, ts DESC);

CREATE INDEX IF NOT EXISTS idx_indicator_values_indicator_ts
    ON market_data.indicator_values (indicator, ts DESC);
