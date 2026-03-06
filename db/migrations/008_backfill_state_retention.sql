ALTER TABLE IF EXISTS market_data.backfill_state
    ADD COLUMN IF NOT EXISTS scan_chunk_index INT,
    ADD COLUMN IF NOT EXISTS chunk_rows INT,
    ADD COLUMN IF NOT EXISTS requested_start_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS requested_end_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rows_written BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dataset_revision TEXT;

DO $$
BEGIN
    PERFORM remove_retention_policy('market_data.candles_1m', if_exists => true);
EXCEPTION WHEN undefined_function THEN
    NULL;
END$$;

DO $$
BEGIN
    PERFORM add_retention_policy(
        'market_data.candles_1m',
        drop_after => INTERVAL '3650 days',
        if_not_exists => true
    );
EXCEPTION WHEN duplicate_object THEN
    NULL;
END$$;
