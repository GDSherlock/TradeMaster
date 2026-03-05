CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS market_data.backfill_state (
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    last_ts TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'idle',
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, symbol, interval)
);

CREATE TABLE IF NOT EXISTS market_data.indicator_state (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    last_processed_ts TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (exchange, symbol, interval)
);

CREATE TABLE IF NOT EXISTS market_data.ingest_heartbeat (
    component TEXT PRIMARY KEY,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'running',
    message TEXT
);

CREATE TABLE IF NOT EXISTS audit.chat_requests (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id TEXT NOT NULL,
    session_id TEXT,
    user_hash TEXT,
    symbol TEXT,
    interval TEXT,
    status TEXT NOT NULL,
    latency_ms INT,
    tokens_in INT,
    tokens_out INT,
    model TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_requests_ts ON audit.chat_requests (ts DESC);
CREATE INDEX IF NOT EXISTS idx_chat_requests_session ON audit.chat_requests (session_id, ts DESC);
