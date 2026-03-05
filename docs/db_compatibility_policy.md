# DB Compatibility Policy (API-facing)

## Scope
- `api-service` must read from versioned `market_data_api` views only.
- API-compatible views use suffix `_v1`, `_v2`, etc.

## Rules
1. Backward-compatible table changes (add table/add column) can be released directly if existing view contracts are unchanged.
2. Breaking changes (drop column/change semantic/change type) must:
   - publish a new view version first (for example `_v2`);
   - keep previous version (for example `_v1`) for at least two frontend release cycles;
   - migrate API queries to the new version after compatibility window.
3. Never make `api-service` depend on producer base tables directly.
4. Each view version must be immutable in shape once published.

## Current v1 Views
- `market_data_api.v_candles_1m_v1`
- `market_data_api.v_indicator_values_v1`
- `market_data_api.v_signal_events_v1`
- `market_data_api.v_signal_rule_configs_v1`
- `market_data_api.v_signal_ml_validation_v1`
- `market_data_api.v_signal_ml_validation_latest_v1`
- `market_data_api.v_signal_ml_training_runs_v1`
- `market_data_api.v_signal_ml_runtime_state_v1`
- `market_data_api.v_signal_ml_drift_checks_v1`
