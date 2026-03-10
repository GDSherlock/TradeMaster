# TradeMaster

## Project Overview
TradeMaster is a local multi-service analytics pipeline for crypto derivatives market observation. It ingests historical and live Binance Futures UM candle data, stores the result in TimescaleDB, computes technical indicators, generates rule-based signal events, runs a shadow ML validator for a subset of signals, and exposes the resulting state through REST/WS APIs, a Next.js dashboard, and a chat explanation service.

The system is designed around a simple engineering principle: keep the database as the shared source of truth, keep consumer reads behind stable API/view contracts, and keep ML additive rather than authoritative. TradeMaster is an analytics and validation stack. It does not execute orders, route trades, or provide automated risk management.

Core design choices:
- Database-first pipeline: raw candles, derived indicators, rule events, and ML outputs are materialized into PostgreSQL/TimescaleDB.
- Stable read layer: `api-service` reads versioned `market_data_api.v_*_v1` views instead of producer base tables.
- Shadow validation: ML annotates selected signals but does not block or replace the rule engine.

## Output / Core Features

| Output / capability | What it provides | Primary producers / consumers |
| --- | --- | --- |
| Historical and live candle store | 1-minute OHLCV in `market_data.candles_1m` | `pipeline-service` writes, all downstream services read |
| Derived indicators | EMA, MACD, RSI, ATR, Bollinger Bands, VWAP, Donchian, Ichimoku in `market_data.indicator_values` | `pipeline-service` writes, `signal-service`, `ml-validator-service`, `api-service`, `chat-service` consume |
| Rule-based signal events | 12 technical signal rules in `market_data.signal_events` | `signal-service` writes, dashboard/API/ML consume |
| Shadow ML validation | Probability, decision, training runs, recalibration, drift checks in `signal_ml_*` tables | `ml-validator-service` writes, `api-service` and dashboard consume |
| Unified read APIs | REST and WebSocket access to market, indicator, signal, and ML data | `api-service`, `signal-service`, `ml-validator-service` |
| Dashboard UI | Market overview, signals, indicator views, ML console, chat UI | `services-preview/web-dashboard` |
| Chat explanation layer | Natural-language market summaries built from live system context | `chat-service` |
| Operational state | Backfill checkpoints, heartbeats, audit logs, security report | DB state tables, `logs/`, `run/pids/` |

## System Architecture

### Service map

| Component | Default port | Runtime role |
| --- | ---: | --- |
| TimescaleDB / PostgreSQL | `5434` | System of record for candles, indicators, signals, ML outputs, state, and audit logs |
| `pipeline-service` live health | `9101` | Live ingestion heartbeat and metrics |
| `pipeline-service` indicator health | `9102` | Indicator scheduler heartbeat and metrics |
| `api-service` | `8000` | Unified REST/WS read layer over versioned DB views |
| `chat-service` | `8001` | Market-context chat API and audit logging |
| `signal-service` | `8002` | Signal REST/WS service and rule-engine host |
| `ml-validator-service` | `8003` | ML runtime, training, drift, and validation service |
| `web-dashboard` | `8088` | Next.js UI and same-origin BFF |

### End-to-end data flow

```text
Hugging Face dataset                         Binance Futures UM
123olp/binance-futures-ohlcv-2018-2026      WS stream + REST klines
                |                                      |
                v                                      v
        pipeline backfill                    live_ws + REST gap fill
                \                              /
                 \                            /
                  +--> market_data.candles_1m
                               |
                               v
                    indicator engine / scheduler
                               |
                               v
                  market_data.indicator_values
                               |
                               v
                    signal rule engine (12 rules)
                               |
                               v
                     market_data.signal_events
                               |
                +--------------+------------------+
                |                                 |
                v                                 v
      RSI signal candidates only         signal-service REST / WS
                |
                v
        ml-validator-service (shadow)
                |
                v
          market_data.signal_ml_*
                |
                v
      market_data_api.v_*_v1 read views
                |
                v
             api-service REST / WS
                |                \
                |                 \--> direct browser WS (default: /ws/signal)
                v
     Next.js same-origin BFF (/api/trademaster/*)
                |
                v
          web-dashboard UI

chat-service -> api-service context fetch -> LLM provider
chat-service -> logs/chat_audit.jsonl and optional audit.chat_requests
```

### Runtime orchestration

TradeMaster runs as local background processes managed by [`Makefile`](./Makefile) and [`scripts/devctl.sh`](./scripts/devctl.sh). There is no Docker Compose or deployment manifest in this repository.

`make dev` starts three process groups:

| Group | Processes |
| --- | --- |
| `data` | `pipeline-live`, `pipeline-indicator`, `signal-engine`, `ml-validate-loop`, `ml-monitor-loop` |
| `edge` | `api-service`, `chat-service`, `signal-service`, `ml-validator-service` |
| `web` | `web-dashboard` |

Runtime files:
- Logs: `logs/`, plus grouped logs under `logs/data/`, `logs/edge/`, and `logs/web/`
- PID files: `run/pids/`
- Hugging Face dataset cache: `data/hf/`

## Project Structure

| Path | Responsibility |
| --- | --- |
| `config/` | Example environment files and local runtime configuration |
| `db/migrations/` | Schema creation for `market_data`, `audit`, ML tables, and versioned API views |
| `docs/` | Cross-service dependency and DB compatibility notes |
| `scripts/` | Bootstrap, DB migration, process orchestration, smoke, ML report, and security check scripts |
| `services/pipeline-service/` | Historical backfill, live market ingestion, indicator engine, heartbeat/metrics |
| `services/signal-service/` | Rule evaluation engine plus signal REST/WS API |
| `services/ml-validator-service/` | Shadow validation worker, model training, recalibration, drift monitoring, ML REST API |
| `services/api-service/` | Unified REST/WS read layer over versioned DB views |
| `services/chat-service/` | Chat endpoint, prompt guardrails, context builder, provider integration, audit logging |
| `services-preview/web-dashboard/` | Next.js dashboard and same-origin BFF for REST/chat requests |
| `db/README.md` | Database-level operational queries and schema overview |
| `logs/`, `run/` | Local runtime artifacts created by scripts |

## Setup / Installation

### Prerequisites

- Python `3.12+` for backend services
- Node.js `20+` and `npm` for the dashboard
- PostgreSQL `16+` with TimescaleDB `2.14+`
- `psql` available in `PATH`

### 1. Install service dependencies

```bash
make init
```

What `make init` does:
- Creates a per-service Python virtual environment under each backend service directory
- Installs each service's `requirements.txt`
- Installs `pip-audit` into `.venv-security`
- Runs `npm install` in `services-preview/web-dashboard`

### 2. Create local configuration

Use the example file as the source of truth:

```bash
cp config/.env.example config/.env
chmod 600 config/.env
```

Minimum required edits:

```bash
AUTH_ENABLED=true
API_TOKEN=<strong-random-token>
API_SERVICE_TOKEN=<same-token-used-by-internal-callers>
CORS_ALLOW_ORIGINS=http://localhost:8088
```

If you want the chat layer:

```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.2
LLM_API_KEY=<your-llm-api-key>
```

Notes:
- Use `config/.env.example` for setup. Do not treat any tracked local `config/.env` in your workspace as a deployment template.
- `config/.env.dev.example` exists for localhost-only debugging. It is not intended for staging or production.
- Outside local development, keep `AUTH_ENABLED=true`, use a non-default token, and restrict CORS to explicit origins.

### 3. Initialize the database

```bash
make db-init
```

This applies all SQL migrations in `db/migrations/`, including:
- base TimescaleDB tables
- indicator/state/audit tables
- signal tables
- ML validation/training/drift/recalibration tables
- versioned `market_data_api` views

### 4. Run the security baseline

```bash
make security-check
```

The report is written to `logs/security_report.md`.

## Usage

### Full local stack

1. Backfill the supported historical symbols:

```bash
make backfill \
  SYMBOLS=BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT \
  START_TS=2020-01-01T00:00:00Z \
  RESUME=1 \
  WITH_INDICATORS=1
```

2. Start the services:

```bash
make dev
make status
```

3. Stop everything:

```bash
make stop
```

### Grouped startup

```bash
make dev-data
make dev-edge
make dev-web
```

Equivalent direct orchestration commands:

```bash
./scripts/devctl.sh start
./scripts/devctl.sh status
./scripts/devctl.sh restart --group web
./scripts/devctl.sh stop
```

### Targeted commands

| Task | Command |
| --- | --- |
| Historical backfill | `make backfill` |
| Live market ingestion only | `make live` |
| Single indicator refresh | `make indicators-once` |
| Indicator scheduler loop | `make indicators-loop` |
| Single signal evaluation pass | `make signal-once` |
| Signal engine loop | `make signal-loop` |
| Signal service only | `make signal` |
| API service only | `make api` |
| Chat service only | `make chat` |
| ML REST service only | `make ml-service` |
| ML validation loop | `make ml-validate-loop` |
| ML monitor loop | `make ml-monitor-loop` |
| Generate ML report | `make ml-report` |
| Security baseline | `make security-check` |

### Runtime access points

| URL | Purpose |
| --- | --- |
| `http://localhost:8000/api/health` | API health |
| `ws://localhost:8000/ws/market` | API market WebSocket |
| `ws://localhost:8000/ws/signal` | API signal WebSocket |
| `http://localhost:8001/health` | Chat health |
| `http://localhost:8002/signal/health` | Signal service health |
| `http://localhost:8003/ml/health` | ML validator health |
| `http://localhost:8088` | Dashboard UI |
| `http://localhost:9101/health` | Pipeline live health |
| `http://localhost:9102/health` | Pipeline indicator health |

### What happens during execution

After startup, the stack operates as a continuous pipeline:
1. `pipeline-service` keeps `candles_1m` current from Binance and can backfill history from Hugging Face.
2. The indicator scheduler derives higher-interval bars from 1-minute data and writes indicator payloads.
3. The signal engine evaluates DB-configured rules and writes edge-triggered signal events with cooldown tracking.
4. The ML validator consumes eligible RSI events, writes shadow decisions, and updates runtime/training/drift state.
5. `api-service` exposes the read model over versioned views.
6. The Next.js dashboard reads through the same-origin BFF, and the browser opens a direct signal WebSocket to `api-service` by default.
7. `chat-service` fetches market context from `api-service`, calls the configured LLM provider, and writes redacted audit records.

### Auth boundary

| Service | Public paths | Protected behavior |
| --- | --- | --- |
| `api-service` | `/health`, `/api/health`, `/docs`, `/openapi.json`, `/redoc` | Other `/api/*` and `/ws/*` require `X-API-Token` when `AUTH_ENABLED=true` |
| `signal-service` | `/signal/health`, `/docs`, `/openapi.json`, `/redoc` | Other `/signal/*` and `/ws/signal` require `X-API-Token` when `AUTH_ENABLED=true` |
| `ml-validator-service` | `/ml/health`, `/docs`, `/openapi.json`, `/redoc` | Other `/ml/*` require `X-API-Token` when `AUTH_ENABLED=true` |
| `chat-service` | `/health`, `POST /chat` | Rate-limited and input-validated, but not token-authenticated in the current implementation |
| `web-dashboard` BFF | Same-origin `GET /api/trademaster/*`, `POST /api/trademaster/chat` | Injects the API token server-side for REST requests; browser does not receive the token |

## Automation / Scheduling

TradeMaster does not use an external scheduler such as cron or Airflow inside this repo. Scheduling is implemented as long-running service loops.

| Process | Default cadence / schedule | Implementation detail |
| --- | --- | --- |
| Live WS ingestion | Continuous | Binance 1-minute closed kline stream |
| WS flush to DB | Every `3s` | Controlled by `WS_FLUSH_SECONDS` |
| REST gap fill | Every `60s` | Controlled by `REST_FALLBACK_INTERVAL_SECONDS` |
| Indicator scheduler | Every `60s` | Controlled by `INDICATOR_SCHEDULE_SECONDS` |
| Signal engine loop | Every `30s` | Controlled by `SIGNAL_SCHEDULE_SECONDS` |
| ML validation loop | Every `30s` | Controlled by `ML_VALIDATE_LOOP_SECONDS` |
| ML monitor loop | Every `60s` | Controlled by `ML_MONITOR_LOOP_SECONDS` |
| ML daily training | `02:10 Asia/Singapore` | Controlled by `ML_TRAIN_SCHEDULE_HOUR` / `MINUTE` |
| ML weekly recalibration | Sunday `02:40 Asia/Singapore` | Controlled by `ML_RECALIBRATE_SCHEDULE_*` |
| ML drift check | Every `6h` | Controlled by `ML_DRIFT_CHECK_HOURS` |
| Dashboard data refresh | Every `15s` by default | Controlled by `NEXT_PUBLIC_REFRESH_INTERVAL_MS`, with signal WS + polling fallback |

## Data Sources / Inputs

| Source | Used by | Data / scope | Reliability notes |
| --- | --- | --- | --- |
| Hugging Face dataset `123olp/binance-futures-ohlcv-2018-2026` (`candles_1m.csv.gz`) | `pipeline-service` backfill | Historical 1-minute OHLCV | Downloaded to `data/hf/`; backfill is symbol-whitelisted in code |
| Binance Futures UM WebSocket `wss://fstream.binance.com/stream` | `pipeline-service` live mode | Live closed 1-minute klines | Reconnects with exponential backoff |
| Binance Futures UM REST `/fapi/v1/klines` | `pipeline-service` live mode | Recent 1-minute klines | Used for gap fill during WS interruptions |
| TimescaleDB `market_data` schema | All services | Raw candles, indicators, signals, ML, state | Shared system of record |
| Versioned `market_data_api.v_*_v1` views | `api-service` | Stable API read contracts | Keeps API queries decoupled from producer table changes |
| Signal rule config table `market_data.signal_rule_configs` | `signal-service` | Enabled flags, priorities, cooldowns, params, symbol/interval scopes | Evaluated on every signal loop |
| External LLM provider | `chat-service` | Natural-language generation | Optional; chat depends on it for model answers |

Data caveats:
- Higher intervals (`5m`, `15m`, `1h`, `4h`, `1d`) are derived from `candles_1m`, not stored as independent raw feeds.
- Historical backfill uses a live guard window to avoid overwriting the most recent live-ingested minutes.
- The dashboard uses REST bootstrap plus WebSocket updates for signals; when WS is unavailable it falls back to periodic fetches.

## Core Logic / Algorithms

### Historical and live ingestion

- `backfill` downloads the configured Hugging Face file, filters it to the supported symbol whitelist, applies the requested time window, and resumes from `market_data.backfill_state` when `RESUME=1`.
- `live` subscribes to Binance 1-minute kline streams, buffers closed candles, flushes them to `market_data.candles_1m`, and periodically performs REST gap fill for recent minutes.
- Both ingestion paths write heartbeats to `market_data.ingest_heartbeat`.

### Indicator generation

- The indicator engine aggregates higher intervals from `candles_1m` using `date_bin`.
- It computes the following indicator tables/payloads:
  - `ema_20`
  - `ema_50`
  - `ema_200`
  - `macd_12_26_9`
  - `rsi_14`
  - `atr_14`
  - `bbands_20`
  - `vwap`
  - `donchian_20`
  - `ichimoku_9_26_52`
- Results are written to `market_data.indicator_values` and used by the signal engine, ML validator, API layer, and chat context builder.

### Signal generation

- `signal-service` reads enabled rule configs from `market_data.signal_rule_configs`, builds a per-symbol/per-interval snapshot from candles + indicators, and writes new events only when a rule crosses into a triggered state.
- Emission is gated by prior event timestamps and DB-backed cooldown state in `market_data.signal_state`.
- Current rule set:
  - `RSI_OVERBOUGHT`
  - `RSI_OVERSOLD`
  - `EMA_BULL_CROSS`
  - `EMA_BEAR_CROSS`
  - `MACD_BULL_CROSS`
  - `MACD_BEAR_CROSS`
  - `DONCHIAN_BREAKOUT_UP`
  - `DONCHIAN_BREAKOUT_DOWN`
  - `VWAP_CROSS_UP`
  - `VWAP_CROSS_DOWN`
  - `ICHIMOKU_CLOUD_BREAK_UP`
  - `ICHIMOKU_CLOUD_BREAK_DOWN`

### ML shadow validation

- The ML validator only processes `RSI_OVERBOUGHT` and `RSI_OVERSOLD` events for the configured interval and symbol set.
- Features are built from the event payload, indicator snapshot, and recent candles. The feature map includes RSI, EMA gaps, MACD values, volatility terms, Donchian/Bollinger/VWAP/Ichimoku position terms, returns, volume context, and cooldown/time context.
- Labels are generated from future price movement using a triple-barrier-style target with ATR-scaled take-profit/stop-loss and a configured horizon. An auxiliary RSI reversion label is also recorded for analysis.
- Training uses `StandardScaler` + `LogisticRegression` with calibrated probabilities. Promotion is gated by precision improvement, PR-AUC non-regression, Brier tolerance, and coverage bounds.
- Outputs are stored in `signal_ml_validation`, `signal_ml_training_runs`, `signal_ml_runtime_state`, `signal_ml_drift_checks`, and `signal_ml_recalibration_runs`.
- The ML path is shadow-only: rule events are still emitted even if ML is unavailable or rejects a candidate.

### API, dashboard, and chat flow

- `api-service` reads only versioned `market_data_api.v_*_v1` views and exposes REST and WebSocket endpoints for market, indicator, signal, and ML consumers.
- The dashboard uses a same-origin BFF:
  - `GET /api/trademaster/[...path]` proxies allowed API GET paths and injects `X-API-Token` server-side.
  - `POST /api/trademaster/chat` proxies chat requests to `chat-service`.
  - The browser's default signal stream is `ws://<host>:8000/ws/signal`.
- `chat-service` performs:
  - message validation and size limits
  - prompt-injection pattern checks
  - sensitive text redaction for audit logs
  - context fetches from `api-service` (`ohlc/history`, indicator list/data, momentum, latest signal)
  - Responses API first, Chat Completions fallback
  - deterministic fallback rendering when structured model output is unavailable

## Configuration

Default values live in [`config/.env.example`](./config/.env.example).

| Area | High-impact variables | What they control |
| --- | --- | --- |
| Core | `DATABASE_URL`, `DEFAULT_EXCHANGE`, `SYMBOLS`, `INTERVALS` | Database target, exchange ID, tracked symbols, derived intervals |
| Security | `AUTH_ENABLED`, `API_TOKEN`, `CORS_ALLOW_ORIGINS` | Token auth and browser-origin policy |
| API | `API_SERVICE_HOST`, `API_SERVICE_PORT`, `API_RATE_LIMIT_PER_MINUTE`, `API_RATE_LIMIT_BURST` | API bind address and rate limiting |
| Pipeline / backfill | `BACKFILL_START_TS`, `BACKFILL_END_TS`, `BACKFILL_WITH_INDICATORS`, `BACKFILL_LIVE_GUARD_MINUTES`, `HF_DATASET`, `HF_CANDLES_FILE` | Historical replay window, indicator backfill, Hugging Face source |
| Pipeline / live | `WS_URL`, `WS_RECONNECT_MAX_SECONDS`, `WS_FLUSH_SECONDS`, `REST_FALLBACK_INTERVAL_SECONDS`, `PIPELINE_SERVICE_HOST`, `PIPELINE_SERVICE_PORT` | Binance stream settings, reconnect behavior, health/metrics bind |
| Indicators | `INDICATOR_SCHEDULE_SECONDS` | Indicator refresh cadence |
| Signals | `SIGNAL_SERVICE_HOST`, `SIGNAL_SERVICE_PORT`, `SIGNAL_SCHEDULE_SECONDS`, `SIGNAL_WS_POLL_SECONDS`, `SIGNAL_RATE_LIMIT_*` | Signal loop cadence and signal service exposure |
| ML | `ML_INTERVAL`, `ML_HORIZON_BARS`, `ML_DECISION_THRESHOLD`, `ML_LOOKBACK_DAYS`, `ML_VAL_DAYS`, `ML_TEST_DAYS`, `ML_TRAIN_SCHEDULE_*`, `ML_RECALIBRATE_SCHEDULE_*`, `ML_DRIFT_CHECK_HOURS`, `ML_DRIFT_PSI_THRESHOLD` | Training scope, label horizon, promotion thresholding, schedule, drift sensitivity |
| Chat | `CHAT_SERVICE_HOST`, `CHAT_SERVICE_PORT`, `CHAT_RATE_LIMIT_PER_MINUTE`, `CHAT_MAX_CONCURRENCY_PER_IP`, `CHAT_MAX_INPUT_CHARS`, `CHAT_MAX_TURNS`, `API_SERVICE_BASE_URL`, `API_SERVICE_TOKEN`, `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_CHARS` | Chat ingress, upstream API access, model provider behavior |
| Dashboard | `WEB_DASHBOARD_HOST`, `WEB_DASHBOARD_PORT`, `CHAT_SERVICE_BASE_URL` | Next.js bind address and chat upstream |

Optional dashboard runtime overrides are read directly by the Next.js app:
- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_CHAT_BASE_URL`
- `NEXT_PUBLIC_SIGNAL_WS_URL`
- `NEXT_PUBLIC_DEFAULT_EXCHANGE`
- `NEXT_PUBLIC_DEFAULT_INTERVAL`
- `NEXT_PUBLIC_DEFAULT_SYMBOL`
- `NEXT_PUBLIC_TREND_SYMBOLS`
- `NEXT_PUBLIC_REFRESH_INTERVAL_MS`

## Current Limitations / Known Issues

- Exchange scope is currently limited to `binance_futures_um`.
- Historical backfill is hard-restricted in code to `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, and `BNBUSDT`.
- Higher intervals are derived from 1-minute candles, so any gap in `candles_1m` propagates into downstream intervals.
- The ML validator only covers RSI overbought/oversold candidates and runs in shadow mode; it does not govern signal emission.
- `chat-service` currently exposes `POST /chat` without token authentication. In practice it should be fronted by local-only access, the dashboard BFF, or additional network controls.
- Naming is not fully unified. The repo and UI use `TradeMaster`, while several FastAPI service titles and `make help` text still say `TradeCat MVP`.
- Automated coverage is uneven. There are contract-style tests for API payload shapes and chat render behavior, but not the same level of automated coverage for pipeline/live ingestion and rule-engine loops.
- The repo currently contains a tracked `config/.env`. Treat `config/.env.example` as the setup baseline instead of any local tracked runtime file.
- This repo documents and runs a local process-managed stack. It does not include a production deployment package, container orchestration, or managed-secret integration.

## Future Improvements

- Unify naming drift between `TradeMaster` and `TradeCat MVP` across service metadata, UI copy, and command help text.
- Expand automated coverage around `pipeline-service`, `signal-service`, and ML scheduling paths.
- Remove reliance on tracked local runtime config as part of the normal setup story and keep secure examples centralized in `config/.env.example`.

## Related Documentation

- [Pipeline service README](./services/pipeline-service/README.md)
- [API service README](./services/api-service/README.md)
- [Chat service README](./services/chat-service/README.md)
- [Signal service README](./services/signal-service/README.md)
- [ML validator service README](./services/ml-validator-service/README.md)
- [Web dashboard README](./services-preview/web-dashboard/README.md)
- [Database README](./db/README.md)
- [Service dependency matrix](./docs/service_dependency_matrix.md)
- [DB compatibility policy](./docs/db_compatibility_policy.md)
