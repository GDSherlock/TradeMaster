#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICES=(
  "services/pipeline-service"
  "services/api-service"
  "services/chat-service"
  "services/signal-service"
)

for svc in "${SERVICES[@]}"; do
  echo "==> init $svc"
  cd "$ROOT/$svc"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  .venv/bin/pip install --upgrade pip >/dev/null
  .venv/bin/pip install -r requirements.txt
  mkdir -p logs pids

done

cd "$ROOT"
mkdir -p run/pids logs
chmod +x scripts/*.sh
chmod +x services-preview/web-dashboard/scripts/start.sh

echo "==> init services-preview/web-dashboard"
if command -v npm >/dev/null 2>&1; then
  cd "$ROOT/services-preview/web-dashboard"
  npm install
else
  echo "WARN: npm not found; skipped web-dashboard dependency install."
fi

echo "init done"
