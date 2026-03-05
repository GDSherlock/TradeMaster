#!/usr/bin/env bash
# web-dashboard Next.js server
# Usage: ./scripts/start.sh {start|stop|status|restart|run}

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SERVICE_DIR")")"
RUN_DIR="$SERVICE_DIR/pids"
LOG_DIR="$SERVICE_DIR/logs"
SERVICE_PID="$RUN_DIR/service.pid"
SERVICE_LOG="$LOG_DIR/service.log"

safe_load_env() {
    local file="$1"
    [ -f "$file" ] || return 0

    if [[ "$file" == *"config/.env" ]] && [[ ! "$file" == *".example" ]]; then
        local perm
        if stat -c %a "$file" >/dev/null 2>&1; then
            perm=$(stat -c %a "$file" 2>/dev/null)
        else
            perm=$(stat -f %A "$file" 2>/dev/null)
        fi
        if [[ "$perm" != "600" && "$perm" != "400" ]]; then
            if [[ "${CODESPACES:-}" == "true" ]]; then
                echo "WARN: Codespace environment, skipping permission check ($file: $perm)"
            else
                echo "Error: $file permission is $perm, must be 600"
                echo "Run: chmod 600 $file"
                exit 1
            fi
        fi
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*export ]] && continue
        [[ "$line" =~ \$\( ]] && continue
        [[ "$line" =~ \` ]] && continue
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local val="${BASH_REMATCH[2]}"
            val="${val#\"}" && val="${val%\"}"
            val="${val#\'}" && val="${val%\'}"
            export "$key=$val"
        fi
    done < "$file"
}

safe_load_env "$PROJECT_ROOT/config/.env"

HOST="${WEB_DASHBOARD_HOST:-0.0.0.0}"
PORT="${WEB_DASHBOARD_PORT:-8088}"
START_CMD="npm run dev -- --hostname $HOST --port $PORT"

init_dirs() {
    mkdir -p "$RUN_DIR" "$LOG_DIR"
}

is_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

get_service_pid() {
    [ -f "$SERVICE_PID" ] && cat "$SERVICE_PID"
}

check_toolchain() {
    if ! command -v node >/dev/null 2>&1; then
        echo "Error: node is not installed. Install Node.js 20+ to run web-dashboard."
        exit 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
        echo "Error: npm is not installed. Install npm to run web-dashboard."
        exit 1
    fi
    if [[ ! -f "$SERVICE_DIR/package.json" ]]; then
        echo "Error: package.json not found in $SERVICE_DIR"
        exit 1
    fi
    if [[ ! -d "$SERVICE_DIR/node_modules" ]]; then
        echo "Error: node_modules not found. Run: cd $SERVICE_DIR && npm install"
        exit 1
    fi
}

start_service() {
    init_dirs
    check_toolchain

    local pid
    pid=$(get_service_pid)
    if is_running "$pid"; then
        echo "OK: Service is already running (PID: $pid)"
        return 0
    fi

    cd "$SERVICE_DIR" || return 1
    nohup bash -lc "$START_CMD" >> "$SERVICE_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$SERVICE_PID"
    sleep 1

    if is_running "$new_pid"; then
        echo "OK: Web dashboard started (PID: $new_pid, port: $PORT)"
    else
        echo "ERROR: Failed to start. Check log: $SERVICE_LOG"
        return 1
    fi
}

run_service() {
    init_dirs
    check_toolchain
    cd "$SERVICE_DIR" || return 1
    exec bash -lc "$START_CMD"
}

stop_service() {
    local pid
    pid=$(get_service_pid)
    if ! is_running "$pid"; then
        echo "Service is not running"
        rm -f "$SERVICE_PID"
        return 0
    fi
    kill "$pid" 2>/dev/null
    sleep 1
    if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$SERVICE_PID"
    echo "OK: Service stopped"
}

status_service() {
    local pid
    pid=$(get_service_pid)
    if is_running "$pid"; then
        echo "OK: Service running (PID: $pid)"
        echo "=== Recent logs ==="
        tail -n 10 "$SERVICE_LOG" 2>/dev/null
    else
        echo "ERROR: Service not running"
    fi
}

case "${1:-status}" in
    start) start_service ;;
    stop) stop_service ;;
    status) status_service ;;
    restart) stop_service; sleep 1; start_service ;;
    run) run_service ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|run}"
        exit 1
        ;;
esac
