#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/config/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "missing config/.env. run: cp config/.env.example config/.env"
  exit 1
fi

if [ "$(stat -f %A "$ENV_FILE" 2>/dev/null || stat -c %a "$ENV_FILE" 2>/dev/null || echo 0)" != "600" ] && \
   [ "$(stat -f %A "$ENV_FILE" 2>/dev/null || stat -c %a "$ENV_FILE" 2>/dev/null || echo 0)" != "400" ]; then
  echo "warning: config/.env permission should be 600 or 400"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required"
  exit 1
fi

for f in "$ROOT"/db/migrations/*.sql; do
  echo "apply $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "db init done"
