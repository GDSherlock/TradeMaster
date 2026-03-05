CREATE SCHEMA IF NOT EXISTS market_data;

CREATE TABLE IF NOT EXISTS market_data.signal_rule_configs (
    rule_key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INT NOT NULL DEFAULT 100,
    cooldown_seconds INT NOT NULL DEFAULT 900,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    scope_symbols TEXT[] NOT NULL DEFAULT '{}',
    scope_intervals TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_data.signal_events (
    id BIGSERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price DOUBLE PRECISION,
    score DOUBLE PRECISION,
    cooldown_seconds INT NOT NULL DEFAULT 0,
    detail TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_signal_events_symbol_interval_ts
    ON market_data.signal_events (symbol, interval, event_ts DESC);

CREATE INDEX IF NOT EXISTS idx_signal_events_detected_at
    ON market_data.signal_events (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_events_rule_ts
    ON market_data.signal_events (rule_key, event_ts DESC);

CREATE TABLE IF NOT EXISTS market_data.signal_state (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    last_status TEXT NOT NULL DEFAULT 'off',
    last_event_ts TIMESTAMPTZ,
    cooldown_until TIMESTAMPTZ,
    last_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (exchange, symbol, interval, rule_key)
);

INSERT INTO market_data.signal_rule_configs (rule_key, priority, cooldown_seconds, params)
VALUES
  ('RSI_OVERBOUGHT', 120, 900, '{"overbought": 70}'),
  ('RSI_OVERSOLD', 120, 900, '{"oversold": 30}'),
  ('EMA_BULL_CROSS', 110, 600, '{}'),
  ('EMA_BEAR_CROSS', 110, 600, '{}'),
  ('MACD_BULL_CROSS', 110, 600, '{}'),
  ('MACD_BEAR_CROSS', 110, 600, '{}'),
  ('DONCHIAN_BREAKOUT_UP', 100, 900, '{}'),
  ('DONCHIAN_BREAKOUT_DOWN', 100, 900, '{}'),
  ('VWAP_CROSS_UP', 100, 600, '{}'),
  ('VWAP_CROSS_DOWN', 100, 600, '{}'),
  ('ICHIMOKU_CLOUD_BREAK_UP', 95, 1200, '{}'),
  ('ICHIMOKU_CLOUD_BREAK_DOWN', 95, 1200, '{}')
ON CONFLICT (rule_key) DO NOTHING;
