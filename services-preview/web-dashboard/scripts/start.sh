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

MAX_START_WAIT_SECONDS=15

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
    [ -f "$SERVICE_PID" ] && tr -d '[:space:]' < "$SERVICE_PID" || true
}

get_port_listener_pid() {
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | awk 'NR==1 { print; exit }'
}

get_pid_cmdline() {
    local pid="$1"
    ps -p "$pid" -o command= 2>/dev/null | sed -e 's/^[[:space:]]*//' || true
}

get_pid_cwd() {
    local pid="$1"
    lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ { sub(/^n/, "", $0); print; exit }' || true
}

is_dashboard_process() {
    local pid="$1"
    if ! is_running "$pid"; then
        return 1
    fi

    local cmd cwd
    cmd="$(get_pid_cmdline "$pid")"
    cwd="$(get_pid_cwd "$pid")"

    if [[ "$cmd" == *"next dev"* || "$cmd" == *"next/dist/bin/next dev"* || "$cmd" == *"npm run dev"* || "$cmd" == *"next-server"* ]]; then
        if [[ "$cmd" == *"$SERVICE_DIR"* || "$cwd" == "$SERVICE_DIR"* ]]; then
            return 0
        fi
    fi

    return 1
}

log_tail() {
    echo "=== Recent logs ($SERVICE_LOG) ==="
    tail -n 40 "$SERVICE_LOG" 2>/dev/null || true
}

current_log_bytes() {
    [ -f "$SERVICE_LOG" ] && wc -c < "$SERVICE_LOG" || echo 0
}

log_has_next_module_missing_since() {
    local start_bytes="${1:-0}"
    [ -f "$SERVICE_LOG" ] || return 1

    local start_pos
    start_pos=$((start_bytes + 1))
    tail -c +"$start_pos" "$SERVICE_LOG" 2>/dev/null | awk '
        /MODULE_NOT_FOUND/ { has_mod = 1 }
        /.next\/server/ { has_next = 1 }
        END { exit !(has_mod && has_next) }
    '
}

normalize_pid_files() {
    init_dirs

    shopt -s nullglob
    local canonical_pid=""
    local pid_file pid
    for pid_file in "$RUN_DIR"/service*.pid; do
        pid="$(tr -d '[:space:]' < "$pid_file" 2>/dev/null || true)"
        if is_dashboard_process "$pid"; then
            if [[ -z "$canonical_pid" ]]; then
                canonical_pid="$pid"
            fi
        else
            rm -f "$pid_file"
        fi
    done

    if [[ -n "$canonical_pid" ]]; then
        echo "$canonical_pid" > "$SERVICE_PID"
    fi

    for pid_file in "$RUN_DIR"/service*.pid; do
        if [[ "$pid_file" != "$SERVICE_PID" ]]; then
            rm -f "$pid_file"
        fi
    done
    shopt -u nullglob
}

resolve_running_dashboard_pid() {
    normalize_pid_files

    local pid
    pid="$(get_service_pid)"
    if is_dashboard_process "$pid"; then
        echo "$pid"
        return 0
    fi

    local listener_pid
    listener_pid="$(get_port_listener_pid)"
    if [[ -n "$listener_pid" ]] && is_dashboard_process "$listener_pid"; then
        echo "$listener_pid" > "$SERVICE_PID"
        echo "$listener_pid"
        return 0
    fi

    return 1
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
    if ! command -v lsof >/dev/null 2>&1; then
        echo "Error: lsof is not installed. Install lsof to run web-dashboard."
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

reuse_or_reject_existing_listener() {
    local listener_pid
    listener_pid="$(get_port_listener_pid)"
    if [[ -z "$listener_pid" ]]; then
        return 1
    fi

    if is_dashboard_process "$listener_pid"; then
        echo "$listener_pid" > "$SERVICE_PID"
        echo "OK: Service is already running (reused PID: $listener_pid, port: $PORT)"
        return 0
    fi

    local cmd
    cmd="$(get_pid_cmdline "$listener_pid")"
    echo "ERROR: Port $PORT is already in use by PID $listener_pid"
    if [[ -n "$cmd" ]]; then
        echo "Command: $cmd"
    fi
    return 2
}

wait_for_ready() {
    local pid="$1"
    local timeout="${2:-$MAX_START_WAIT_SECONDS}"
    local sec
    for ((sec=1; sec<=timeout; sec++)); do
        if ! is_running "$pid"; then
            return 1
        fi

        local listener_pid
        listener_pid="$(get_port_listener_pid)"
        if [[ -n "$listener_pid" ]] && is_dashboard_process "$listener_pid"; then
            echo "$listener_pid" > "$SERVICE_PID"
            return 0
        fi
        sleep 1
    done
    return 1
}

start_once() {
    cd "$SERVICE_DIR" || return 1
    nohup bash -lc "$START_CMD" >> "$SERVICE_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$SERVICE_PID"

    if wait_for_ready "$new_pid" "$MAX_START_WAIT_SECONDS"; then
        local ready_pid
        ready_pid="$(get_service_pid)"
        echo "OK: Web dashboard started (PID: $ready_pid, port: $PORT)"
        return 0
    fi

    if is_running "$new_pid"; then
        kill "$new_pid" 2>/dev/null || true
        sleep 1
        if is_running "$new_pid"; then
            kill -9 "$new_pid" 2>/dev/null || true
        fi
    fi
    rm -f "$SERVICE_PID"
    return 1
}

start_service() {
    init_dirs
    check_toolchain

    local running_pid
    if running_pid="$(resolve_running_dashboard_pid)"; then
        echo "OK: Service is already running (PID: $running_pid)"
        return 0
    fi

    local listener_result=1
    if reuse_or_reject_existing_listener; then
        return 0
    else
        listener_result=$?
        if [[ "$listener_result" -eq 2 ]]; then
            return 1
        fi
    fi

    local log_bytes_before_start
    log_bytes_before_start="$(current_log_bytes)"

    if start_once; then
        return 0
    fi

    if log_has_next_module_missing_since "$log_bytes_before_start"; then
        echo "WARN: Detected .next module cache issue. Cleaning .next and retrying once."
        rm -rf "$SERVICE_DIR/.next"
        if start_once; then
            echo "OK: Web dashboard recovered after cache cleanup."
            return 0
        fi
    fi

    echo "ERROR: Failed to start. Check log: $SERVICE_LOG"
    log_tail
    return 1
}

run_service() {
    init_dirs
    check_toolchain
    cd "$SERVICE_DIR" || return 1
    exec bash -lc "$START_CMD"
}

stop_service() {
    local pid=""
    if ! pid="$(resolve_running_dashboard_pid)"; then
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
    local pid=""
    if pid="$(resolve_running_dashboard_pid)"; then
        echo "OK: Service running (PID: $pid)"
        echo "=== Recent logs ==="
        tail -n 10 "$SERVICE_LOG" 2>/dev/null || true
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
