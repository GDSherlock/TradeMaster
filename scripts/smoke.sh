#!/usr/bin/env bash
set -euo pipefail

BASE_API="${BASE_API:-http://localhost:8000}"
BASE_CHAT="${BASE_CHAT:-http://localhost:8001}"
BASE_SIGNAL="${BASE_SIGNAL:-http://localhost:8002}"

curl -fsS "$BASE_API/api/health" >/dev/null
curl -fsS "$BASE_API/api/futures/supported-coins" >/dev/null
curl -fsS "$BASE_API/api/futures/ohlc/history?symbol=BTCUSDT&interval=1h&limit=2" >/dev/null
curl -fsS "$BASE_API/api/indicator/list" >/dev/null
curl -fsS "$BASE_API/api/signal/cooldown" >/dev/null
curl -fsS "$BASE_CHAT/health" >/dev/null
curl -fsS "$BASE_SIGNAL/signal/health" >/dev/null
curl -fsS "$BASE_SIGNAL/signal/cooldown" >/dev/null

echo "smoke passed"
