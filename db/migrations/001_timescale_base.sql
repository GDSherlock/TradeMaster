CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE OR REPLACE FUNCTION market_data.source_priority(src TEXT)
RETURNS INT
LANGUAGE SQL
IMMUTABLE
AS $$
  SELECT CASE COALESCE(src, '')
    WHEN 'hf_backfill' THEN 300
    WHEN 'rest_gap_fill' THEN 200
    WHEN 'ws_live' THEN 100
    ELSE 0
  END;
$$;

CREATE TABLE IF NOT EXISTS market_data.candles_1m (
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    bucket_ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(38, 12) NOT NULL,
    high NUMERIC(38, 12) NOT NULL,
    low NUMERIC(38, 12) NOT NULL,
    close NUMERIC(38, 12) NOT NULL,
    volume NUMERIC(38, 12) NOT NULL,
    quote_volume NUMERIC(38, 12),
    trade_count BIGINT,
    is_closed BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (exchange, symbol, bucket_ts)
);

SELECT create_hypertable(
    'market_data.candles_1m',
    'bucket_ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_candles_1m_symbol_time
    ON market_data.candles_1m (symbol, bucket_ts DESC);

CREATE INDEX IF NOT EXISTS idx_candles_1m_exchange_symbol_time
    ON market_data.candles_1m (exchange, symbol, bucket_ts DESC);

ALTER TABLE IF EXISTS market_data.candles_1m
    SET (
      timescaledb.compress = TRUE,
      timescaledb.compress_segmentby = 'exchange,symbol',
      timescaledb.compress_orderby = 'bucket_ts DESC'
    );

DO $$
BEGIN
    PERFORM add_compression_policy('market_data.candles_1m', INTERVAL '7 days');
EXCEPTION WHEN duplicate_object THEN
    NULL;
END$$;

DO $$
BEGIN
    PERFORM add_retention_policy('market_data.candles_1m', INTERVAL '365 days');
EXCEPTION WHEN duplicate_object THEN
    NULL;
END$$;
