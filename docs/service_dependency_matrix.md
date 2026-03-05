# Service Dependency Matrix

## Service Write/Read/External Calls
| Service | Writes | Reads | External Calls |
| --- | --- | --- | --- |
| `pipeline-service` | `market_data.candles_1m`, `market_data.indicator_values`, `market_data.backfill_state`, `market_data.indicator_state`, `market_data.ingest_heartbeat` | `market_data.candles_1m`, `market_data.backfill_state`, `market_data.indicator_state` | Binance WS, Binance REST, HuggingFace dataset |
| `signal-service` | `market_data.signal_events`, `market_data.signal_state`, `market_data.ingest_heartbeat` | `market_data.indicator_values`, `market_data.candles_1m`, `market_data.signal_rule_configs`, `market_data.signal_state`, `market_data.signal_events` | None |
| `ml-validator-service` | `market_data.signal_ml_validation`, `market_data.signal_ml_training_runs`, `market_data.signal_ml_runtime_state`, `market_data.signal_ml_drift_checks`, `market_data.signal_ml_recalibration_runs` | `market_data.signal_events`, `market_data.indicator_values`, `market_data.candles_1m`, `market_data.signal_ml_*` | None |
| `api-service` | None | `market_data_api.v_*_v1` views only | None |
| `chat-service` | `audit.chat_requests` (optional DB audit), local audit file | via `api-service` REST only | `api-service`, LLM provider |
| `web-dashboard` | None | via same-origin BFF only (`/api/trademaster/*`) | `api-service` and `chat-service` only through Next.js BFF |

## Frontend Request Entry Points
| Purpose | Entry | Upstream |
| --- | --- | --- |
| Market/indicator/signal/ml GET | `/api/trademaster/[...path]` | `api-service` (`/api/*`) |
| Chat POST | `/api/trademaster/chat` | `chat-service` (`/chat`) |
| Signal WS | `NEXT_PUBLIC_SIGNAL_WS_URL` (default `ws://<host>:8000/ws/signal`) | `api-service` WS |

## Token Injection Path
1. Browser sends same-origin request to Next.js BFF.
2. BFF injects `X-API-Token` from server env (`API_SERVICE_TOKEN` fallback `API_TOKEN`) for API GET proxy.
3. Token never exposed in browser-side `NEXT_PUBLIC_*` variables.
