#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/run/pids"
LOG_DIR="$ROOT/logs"
RUN_DATA_DIR="$RUN_DIR/data"
RUN_EDGE_DIR="$RUN_DIR/edge"
RUN_WEB_DIR="$RUN_DIR/web"
LOG_DATA_DIR="$LOG_DIR/data"
LOG_EDGE_DIR="$LOG_DIR/edge"
LOG_WEB_DIR="$LOG_DIR/web"
mkdir -p "$RUN_DATA_DIR" "$RUN_EDGE_DIR" "$RUN_WEB_DIR" "$LOG_DATA_DIR" "$LOG_EDGE_DIR" "$LOG_WEB_DIR"

PIPELINE_LIVE_PID="$RUN_DATA_DIR/pipeline-live.pid"
PIPELINE_INDICATOR_PID="$RUN_DATA_DIR/pipeline-indicator.pid"
SIGNAL_ENGINE_PID="$RUN_DATA_DIR/signal-engine.pid"
ML_VALIDATE_LOOP_PID="$RUN_DATA_DIR/ml-validate-loop.pid"
ML_MONITOR_LOOP_PID="$RUN_DATA_DIR/ml-monitor-loop.pid"

API_PID="$RUN_EDGE_DIR/api-service.pid"
CHAT_PID="$RUN_EDGE_DIR/chat-service.pid"
SIGNAL_SERVICE_PID="$RUN_EDGE_DIR/signal-service.pid"
ML_VALIDATOR_SERVICE_PID="$RUN_EDGE_DIR/ml-validator-service.pid"

WEB_DASHBOARD_PID="$RUN_WEB_DIR/web-dashboard.pid"
WEB_REQUIRED="${DEVCTL_WEB_REQUIRED:-0}"

LEGACY_PIPELINE_PID="$RUN_DIR/pipeline.pid"
LEGACY_PIPELINE_INDICATOR_PID="$RUN_DIR/pipeline-indicator.pid"
LEGACY_SIGNAL_PID="$RUN_DIR/signal.pid"
LEGACY_ML_VALIDATOR_PID="$RUN_DIR/ml-validator.pid"
LEGACY_API_PID="$RUN_DIR/api.pid"
LEGACY_CHAT_PID="$RUN_DIR/chat.pid"

usage() {
  cat <<'USAGE'
usage: ./scripts/devctl.sh {start|stop|restart|status} [--group all|data|edge|web]

examples:
  ./scripts/devctl.sh start
  ./scripts/devctl.sh start --group data
  ./scripts/devctl.sh restart --group web

env:
  DEVCTL_WEB_REQUIRED=1  # when group=all, fail if web-dashboard fails
USAGE
}

is_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local f="$1"
  [ -f "$f" ] && cat "$f" || true
}

resolve_running_pid() {
  local primary_pid_file="$1"
  shift
  local pid_file
  for pid_file in "$primary_pid_file" "$@"; do
    local pid
    pid="$(read_pid "$pid_file")"
    if is_running "$pid"; then
      echo "$pid"
      return 0
    fi
  done
  return 1
}

cleanup_pid_files() {
  local pid_file
  for pid_file in "$@"; do
    rm -f "$pid_file"
  done
}

start_python_service() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local pid_file="$4"
  local log_file="$5"
  shift 5
  local legacy_pid_files=("$@")

  local pid=""
  if pid="$(resolve_running_pid "$pid_file" "${legacy_pid_files[@]-}")"; then
    echo "$name already running (pid=$pid)"
    echo "$pid" > "$pid_file"
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
  shift 2
  local legacy_pid_files=("$@")

  local pid=""
  if ! pid="$(resolve_running_pid "$pid_file" "${legacy_pid_files[@]-}")"; then
    echo "$name not running"
    cleanup_pid_files "$pid_file" "${legacy_pid_files[@]-}"
    return
  fi

  kill "$pid" || true
  sleep 1
  if is_running "$pid"; then
    kill -9 "$pid" || true
  fi
  cleanup_pid_files "$pid_file" "${legacy_pid_files[@]-}"
  echo "$name stopped"
}

status_python_service() {
  local name="$1"
  local pid_file="$2"
  shift 2
  local legacy_pid_files=("$@")

  local pid=""
  if pid="$(resolve_running_pid "$pid_file" "${legacy_pid_files[@]-}")"; then
    echo "$pid" > "$pid_file"
    echo "[ok] $name pid=$pid"
  else
    echo "[--] $name"
  fi
}

start_web() {
  cd "$ROOT/services-preview/web-dashboard"
  if ./scripts/start.sh start; then
    local dashboard_pid
    dashboard_pid="$(cat "$ROOT/services-preview/web-dashboard/pids/service.pid" 2>/dev/null || true)"
    if is_running "$dashboard_pid"; then
      echo "$dashboard_pid" > "$WEB_DASHBOARD_PID"
    fi
    echo "web-dashboard started"
  else
    echo "web-dashboard failed to start. Check: $ROOT/services-preview/web-dashboard/logs/service.log"
    return 1
  fi
}

stop_web() {
  cd "$ROOT/services-preview/web-dashboard"
  ./scripts/start.sh stop >/dev/null 2>&1 || true
  rm -f "$WEB_DASHBOARD_PID"
  echo "web-dashboard stop requested"
}

status_web() {
  local dashboard_pid
  dashboard_pid="$(cat "$ROOT/services-preview/web-dashboard/pids/service.pid" 2>/dev/null || true)"
  if is_running "$dashboard_pid"; then
    echo "$dashboard_pid" > "$WEB_DASHBOARD_PID"
    echo "[ok] web-dashboard pid=$dashboard_pid"
  else
    rm -f "$WEB_DASHBOARD_PID"
    echo "[--] web-dashboard"
  fi
}

start_data() {
  start_python_service "pipeline-live" "$ROOT/services/pipeline-service" ".venv/bin/python -m src live" "$PIPELINE_LIVE_PID" "$LOG_DATA_DIR/pipeline-live.log" "$LEGACY_PIPELINE_PID"
  start_python_service "pipeline-indicator" "$ROOT/services/pipeline-service" "PIPELINE_SERVICE_PORT=\${PIPELINE_INDICATOR_PORT:-9102} .venv/bin/python -m src indicator" "$PIPELINE_INDICATOR_PID" "$LOG_DATA_DIR/pipeline-indicator.log" "$LEGACY_PIPELINE_INDICATOR_PID"
  start_python_service "signal-engine" "$ROOT/services/signal-service" ".venv/bin/python -m src engine" "$SIGNAL_ENGINE_PID" "$LOG_DATA_DIR/signal-engine.log"
  start_python_service "ml-validate-loop" "$ROOT/services/ml-validator-service" ".venv/bin/python -m src validate" "$ML_VALIDATE_LOOP_PID" "$LOG_DATA_DIR/ml-validate-loop.log"
  start_python_service "ml-monitor-loop" "$ROOT/services/ml-validator-service" ".venv/bin/python -m src monitor-loop" "$ML_MONITOR_LOOP_PID" "$LOG_DATA_DIR/ml-monitor-loop.log"
}

stop_data() {
  stop_python_service "pipeline-live" "$PIPELINE_LIVE_PID" "$LEGACY_PIPELINE_PID"
  stop_python_service "pipeline-indicator" "$PIPELINE_INDICATOR_PID" "$LEGACY_PIPELINE_INDICATOR_PID"
  stop_python_service "signal-engine" "$SIGNAL_ENGINE_PID"
  stop_python_service "ml-validate-loop" "$ML_VALIDATE_LOOP_PID"
  stop_python_service "ml-monitor-loop" "$ML_MONITOR_LOOP_PID"
}

status_data() {
  status_python_service "pipeline-live" "$PIPELINE_LIVE_PID" "$LEGACY_PIPELINE_PID"
  status_python_service "pipeline-indicator" "$PIPELINE_INDICATOR_PID" "$LEGACY_PIPELINE_INDICATOR_PID"
  status_python_service "signal-engine" "$SIGNAL_ENGINE_PID"
  status_python_service "ml-validate-loop" "$ML_VALIDATE_LOOP_PID"
  status_python_service "ml-monitor-loop" "$ML_MONITOR_LOOP_PID"
}

start_edge() {
  start_python_service "api-service" "$ROOT/services/api-service" ".venv/bin/python -m src" "$API_PID" "$LOG_EDGE_DIR/api-service.log" "$LEGACY_API_PID"
  start_python_service "chat-service" "$ROOT/services/chat-service" ".venv/bin/python -m src" "$CHAT_PID" "$LOG_EDGE_DIR/chat-service.log" "$LEGACY_CHAT_PID"
  start_python_service "signal-service" "$ROOT/services/signal-service" ".venv/bin/python -m src serve" "$SIGNAL_SERVICE_PID" "$LOG_EDGE_DIR/signal-service.log" "$LEGACY_SIGNAL_PID"
  start_python_service "ml-validator-service" "$ROOT/services/ml-validator-service" ".venv/bin/python -m src serve" "$ML_VALIDATOR_SERVICE_PID" "$LOG_EDGE_DIR/ml-validator-service.log" "$LEGACY_ML_VALIDATOR_PID"
}

stop_edge() {
  stop_python_service "api-service" "$API_PID" "$LEGACY_API_PID"
  stop_python_service "chat-service" "$CHAT_PID" "$LEGACY_CHAT_PID"
  stop_python_service "signal-service" "$SIGNAL_SERVICE_PID" "$LEGACY_SIGNAL_PID"
  stop_python_service "ml-validator-service" "$ML_VALIDATOR_SERVICE_PID" "$LEGACY_ML_VALIDATOR_PID"
}

status_edge() {
  status_python_service "api-service" "$API_PID" "$LEGACY_API_PID"
  status_python_service "chat-service" "$CHAT_PID" "$LEGACY_CHAT_PID"
  status_python_service "signal-service" "$SIGNAL_SERVICE_PID" "$LEGACY_SIGNAL_PID"
  status_python_service "ml-validator-service" "$ML_VALIDATOR_SERVICE_PID" "$LEGACY_ML_VALIDATOR_PID"
}

start_group() {
  case "$1" in
    all)
      start_data
      start_edge
      if ! start_web; then
        echo "[warn] web-dashboard failed, but data/edge services remain running."
        echo "[warn] check log: $ROOT/services-preview/web-dashboard/logs/service.log"
        if [[ "$WEB_REQUIRED" == "1" ]]; then
          return 1
        fi
      fi
      ;;
    data) start_data ;;
    edge) start_edge ;;
    web) start_web ;;
    *)
      echo "invalid group: $1"
      usage
      exit 1
      ;;
  esac
}

stop_group() {
  case "$1" in
    all)
      stop_web
      stop_edge
      stop_data
      ;;
    data) stop_data ;;
    edge) stop_edge ;;
    web) stop_web ;;
    *)
      echo "invalid group: $1"
      usage
      exit 1
      ;;
  esac
}

status_group() {
  case "$1" in
    all)
      status_data
      status_edge
      status_web
      ;;
    data) status_data ;;
    edge) status_edge ;;
    web) status_web ;;
    *)
      echo "invalid group: $1"
      usage
      exit 1
      ;;
  esac
}

ACTION="${1:-status}"
if [[ $# -gt 0 ]]; then
  shift
fi

GROUP="all"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --group)
      GROUP="${2:-}"
      shift 2
      ;;
    --group=*)
      GROUP="${1#*=}"
      shift
      ;;
    *)
      echo "unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "$GROUP" != "all" && "$GROUP" != "data" && "$GROUP" != "edge" && "$GROUP" != "web" ]]; then
  echo "invalid group: $GROUP"
  usage
  exit 1
fi

case "$ACTION" in
  start)
    start_group "$GROUP"
    ;;
  stop)
    stop_group "$GROUP"
    ;;
  restart)
    stop_group "$GROUP"
    sleep 1
    start_group "$GROUP"
    ;;
  status)
    status_group "$GROUP"
    ;;
  *)
    usage
    exit 1
    ;;
esac
