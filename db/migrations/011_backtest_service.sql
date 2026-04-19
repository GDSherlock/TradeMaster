CREATE TABLE IF NOT EXISTS market_data.backtest_strategies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_data.backtest_strategy_versions (
    id BIGSERIAL PRIMARY KEY,
    strategy_id BIGINT NOT NULL REFERENCES market_data.backtest_strategies (id) ON DELETE CASCADE,
    version_no INT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    dsl_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_backtest_strategy_version UNIQUE (strategy_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_backtest_strategy_versions_strategy_id
    ON market_data.backtest_strategy_versions (strategy_id, version_no DESC);

CREATE TABLE IF NOT EXISTS market_data.backtest_runs (
    id BIGSERIAL PRIMARY KEY,
    strategy_id BIGINT NOT NULL REFERENCES market_data.backtest_strategies (id) ON DELETE CASCADE,
    strategy_version_id BIGINT NOT NULL REFERENCES market_data.backtest_strategy_versions (id) ON DELETE RESTRICT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    run_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_backtest_runs_status CHECK (status IN ('queued', 'running', 'completed', 'failed', 'canceled')),
    CONSTRAINT chk_backtest_runs_window CHECK (end_ts > start_ts)
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_status_queue
    ON market_data.backtest_runs (status, queued_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy_created_at
    ON market_data.backtest_runs (strategy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS market_data.backtest_run_trades (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES market_data.backtest_runs (id) ON DELETE CASCADE,
    trade_no INT NOT NULL,
    side TEXT NOT NULL,
    entry_ts TIMESTAMPTZ NOT NULL,
    exit_ts TIMESTAMPTZ NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    notional DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    leverage DOUBLE PRECISION NOT NULL,
    gross_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    net_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    fees_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    slippage_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    bars_held INT NOT NULL DEFAULT 0,
    exit_reason TEXT NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_backtest_run_trade_no UNIQUE (run_id, trade_no),
    CONSTRAINT chk_backtest_run_trade_side CHECK (side IN ('long', 'short'))
);

CREATE INDEX IF NOT EXISTS idx_backtest_run_trades_run_id
    ON market_data.backtest_run_trades (run_id, trade_no ASC);

CREATE TABLE IF NOT EXISTS market_data.backtest_run_equity_points (
    run_id BIGINT NOT NULL REFERENCES market_data.backtest_runs (id) ON DELETE CASCADE,
    point_no INT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    close_price DOUBLE PRECISION NOT NULL,
    equity DOUBLE PRECISION NOT NULL,
    cash_balance DOUBLE PRECISION NOT NULL,
    peak_equity DOUBLE PRECISION NOT NULL,
    total_drawdown_pct DOUBLE PRECISION NOT NULL,
    trailing_drawdown_pct DOUBLE PRECISION NOT NULL,
    position_side TEXT,
    position_notional DOUBLE PRECISION NOT NULL DEFAULT 0,
    position_quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, point_no),
    CONSTRAINT chk_backtest_run_equity_side CHECK (position_side IN ('long', 'short') OR position_side IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_backtest_run_equity_points_ts
    ON market_data.backtest_run_equity_points (run_id, ts ASC);

CREATE TABLE IF NOT EXISTS market_data.backtest_run_events (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES market_data.backtest_runs (id) ON DELETE CASCADE,
    event_ts TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_backtest_run_events_severity CHECK (severity IN ('info', 'warn', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_backtest_run_events_run_id
    ON market_data.backtest_run_events (run_id, event_ts ASC, id ASC);

DROP VIEW IF EXISTS market_data_api.v_backtest_strategies_v1;
CREATE VIEW market_data_api.v_backtest_strategies_v1 AS
WITH latest_versions AS (
    SELECT DISTINCT ON (strategy_id)
           id AS latest_version_id,
           strategy_id,
           version_no AS latest_version_no,
           exchange,
           symbol,
           interval,
           dsl_json,
           created_at AS latest_version_created_at
    FROM market_data.backtest_strategy_versions
    ORDER BY strategy_id, version_no DESC
)
SELECT s.id,
       s.name,
       s.description,
       lv.latest_version_id,
       lv.latest_version_no,
       lv.exchange,
       lv.symbol,
       lv.interval,
       lv.dsl_json,
       lv.latest_version_created_at,
       s.created_at,
       s.updated_at
FROM market_data.backtest_strategies s
LEFT JOIN latest_versions lv ON lv.strategy_id = s.id;

DROP VIEW IF EXISTS market_data_api.v_backtest_strategy_versions_v1;
CREATE VIEW market_data_api.v_backtest_strategy_versions_v1 AS
SELECT id,
       strategy_id,
       version_no,
       exchange,
       symbol,
       interval,
       dsl_json,
       created_at
FROM market_data.backtest_strategy_versions;

DROP VIEW IF EXISTS market_data_api.v_backtest_runs_v1;
CREATE VIEW market_data_api.v_backtest_runs_v1 AS
SELECT r.id,
       r.strategy_id,
       r.strategy_version_id,
       v.version_no,
       s.name AS strategy_name,
       s.description AS strategy_description,
       r.exchange,
       r.symbol,
       r.interval,
       r.start_ts,
       r.end_ts,
       r.status,
       r.run_params,
       r.summary_json,
       r.error_code,
       r.error_message,
       r.queued_at,
       r.started_at,
       r.finished_at,
       r.canceled_at,
       r.created_at,
       r.updated_at
FROM market_data.backtest_runs r
JOIN market_data.backtest_strategies s ON s.id = r.strategy_id
JOIN market_data.backtest_strategy_versions v ON v.id = r.strategy_version_id;

DROP VIEW IF EXISTS market_data_api.v_backtest_run_trades_v1;
CREATE VIEW market_data_api.v_backtest_run_trades_v1 AS
SELECT id,
       run_id,
       trade_no,
       side,
       entry_ts,
       exit_ts,
       entry_price,
       exit_price,
       notional,
       quantity,
       leverage,
       gross_pnl,
       net_pnl,
       fees_paid,
       slippage_paid,
       bars_held,
       exit_reason,
       meta
FROM market_data.backtest_run_trades;

DROP VIEW IF EXISTS market_data_api.v_backtest_run_equity_points_v1;
CREATE VIEW market_data_api.v_backtest_run_equity_points_v1 AS
SELECT run_id,
       point_no,
       ts,
       close_price,
       equity,
       cash_balance,
       peak_equity,
       total_drawdown_pct,
       trailing_drawdown_pct,
       position_side,
       position_notional,
       position_quantity
FROM market_data.backtest_run_equity_points;

DROP VIEW IF EXISTS market_data_api.v_backtest_run_events_v1;
CREATE VIEW market_data_api.v_backtest_run_events_v1 AS
SELECT id,
       run_id,
       event_ts,
       event_type,
       severity,
       message,
       payload
FROM market_data.backtest_run_events;
