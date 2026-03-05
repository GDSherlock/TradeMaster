#!/usr/bin/env bash
set -euo pipefail

BASE_API="${BASE_API:-http://localhost:8000}"
BASE_CHAT="${BASE_CHAT:-http://localhost:8001}"
BASE_SIGNAL="${BASE_SIGNAL:-http://localhost:8002}"
BASE_ML="${BASE_ML:-http://localhost:8003}"

AUTH_ARGS=()
if [[ -n "${API_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "X-API-Token: ${API_TOKEN}")
fi

curl_with_auth() {
  if [[ ${#AUTH_ARGS[@]} -gt 0 ]]; then
    curl -fsS "${AUTH_ARGS[@]}" "$1" >/dev/null
    return
  fi
  curl -fsS "$1" >/dev/null
}

curl -fsS "$BASE_API/api/health" >/dev/null
curl_with_auth "$BASE_API/api/futures/supported-coins"
curl_with_auth "$BASE_API/api/futures/ohlc/history?symbol=BTCUSDT&interval=1h&limit=2"
curl_with_auth "$BASE_API/api/indicator/list"
curl_with_auth "$BASE_API/api/signal/cooldown"
curl -fsS "$BASE_CHAT/health" >/dev/null
curl -fsS "$BASE_SIGNAL/signal/health" >/dev/null
curl_with_auth "$BASE_SIGNAL/signal/cooldown"
curl -fsS "$BASE_ML/ml/health" >/dev/null
curl_with_auth "$BASE_API/api/ml/validation/summary?window=1d"
curl_with_auth "$BASE_API/api/ml/runtime"
curl_with_auth "$BASE_API/api/ml/training/runs?limit=1"
curl_with_auth "$BASE_API/api/ml/drift/latest?limit=1"

echo "smoke passed"
