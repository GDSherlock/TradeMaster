#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/run/pids"
LOG_DIR="$ROOT/logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

PIPELINE_PID="$RUN_DIR/pipeline.pid"
PIPELINE_INDICATOR_PID="$RUN_DIR/pipeline-indicator.pid"
API_PID="$RUN_DIR/api.pid"
CHAT_PID="$RUN_DIR/chat.pid"
SIGNAL_PID="$RUN_DIR/signal.pid"

is_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local f="$1"
  [ -f "$f" ] && cat "$f" || true
}

start_python_service() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local pid_file="$4"
  local log_file="$5"

  local pid
  pid="$(read_pid "$pid_file")"
  if is_running "$pid"; then
    echo "$name already running (pid=$pid)"
    return
  fi

  cd "$workdir"
  nohup bash -lc "$cmd" >> "$log_file" 2>&1 &
  echo $! > "$pid_file"
  sleep 1
  pid="$(read_pid "$pid_file")"
  if is_running "$pid"; then
    echo "$name started (pid=$pid)"
  else
    echo "$name failed to start"
    exit 1
  fi
}

stop_python_service() {
  local name="$1"
  local pid_file="$2"
  local pid
  pid="$(read_pid "$pid_file")"
  if ! is_running "$pid"; then
    echo "$name not running"
    rm -f "$pid_file"
    return
  fi
  kill "$pid" || true
  sleep 1
  if is_running "$pid"; then
    kill -9 "$pid" || true
  fi
  rm -f "$pid_file"
  echo "$name stopped"
}

status_python_service() {
  local name="$1"
  local pid_file="$2"
  local pid
  pid="$(read_pid "$pid_file")"
  if is_running "$pid"; then
    echo "[ok] $name pid=$pid"
  else
    echo "[--] $name"
  fi
}

start_all() {
  start_python_service "pipeline-live" "$ROOT/services/pipeline-service" ".venv/bin/python -m src live" "$PIPELINE_PID" "$LOG_DIR/pipeline-live.log"
  start_python_service "pipeline-indicator" "$ROOT/services/pipeline-service" "PIPELINE_SERVICE_PORT=\${PIPELINE_INDICATOR_PORT:-9102} .venv/bin/python -m src indicator" "$PIPELINE_INDICATOR_PID" "$LOG_DIR/pipeline-indicator.log"
  start_python_service "api" "$ROOT/services/api-service" ".venv/bin/python -m src" "$API_PID" "$LOG_DIR/api.log"
  start_python_service "chat" "$ROOT/services/chat-service" ".venv/bin/python -m src" "$CHAT_PID" "$LOG_DIR/chat.log"
  start_python_service "signal" "$ROOT/services/signal-service" ".venv/bin/python -m src all" "$SIGNAL_PID" "$LOG_DIR/signal.log"

  cd "$ROOT/services-preview/web-dashboard"
  if ./scripts/start.sh start; then
    echo "dashboard started"
  else
    echo "dashboard failed to start. Check: $ROOT/services-preview/web-dashboard/logs/service.log"
    exit 1
  fi
}

stop_all() {
  stop_python_service "pipeline-live" "$PIPELINE_PID"
  stop_python_service "pipeline-indicator" "$PIPELINE_INDICATOR_PID"
  stop_python_service "api" "$API_PID"
  stop_python_service "chat" "$CHAT_PID"
  stop_python_service "signal" "$SIGNAL_PID"
  cd "$ROOT/services-preview/web-dashboard"
  ./scripts/start.sh stop >/dev/null 2>&1 || true
  echo "dashboard stop requested"
}

status_all() {
  status_python_service "pipeline-live" "$PIPELINE_PID"
  status_python_service "pipeline-indicator" "$PIPELINE_INDICATOR_PID"
  status_python_service "api" "$API_PID"
  status_python_service "chat" "$CHAT_PID"
  status_python_service "signal" "$SIGNAL_PID"
  cd "$ROOT/services-preview/web-dashboard"
  ./scripts/start.sh status || true
}

case "${1:-status}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; sleep 1; start_all ;;
  status) status_all ;;
  *)
    echo "usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
