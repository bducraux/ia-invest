#!/usr/bin/env bash
# Para todos os serviços iniciados por scripts/start.sh.
# Usa pidfiles em .dev-logs/pids/ e, como fallback, mata processos
# escutando nas portas 8010 (API) e 3000 (frontend).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PID_DIR="${IA_INVEST_DEV_PID_DIR:-$ROOT/.dev-logs/pids}"

killed_any=0

kill_tree() {
    local pid="$1"
    # mata o processo e todos os descendentes (uvicorn --reload e next dev fazem fork)
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    for c in $children; do
        kill_tree "$c"
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
    fi
}

stop_pidfile() {
    local name="$1"
    local pidfile="$PID_DIR/${name}.pid"
    [ -f "$pidfile" ] || return 0
    local pid
    pid=$(cat "$pidfile" 2>/dev/null || echo "")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "==> [$name] parando pid=$pid"
        kill_tree "$pid"
        killed_any=1
    fi
    rm -f "$pidfile"
}

stop_port() {
    local label="$1"
    local port="$2"
    local pids
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "==> [$label] processo(s) na porta $port: $pids"
        for pid in $pids; do
            kill_tree "$pid"
        done
        killed_any=1
    fi
}

# 1) tenta pelos pidfiles
for name in api frontend mcp; do
    stop_pidfile "$name"
done

# 2) fallback por porta (caso o start tenha sido em outro shell e o pidfile suma)
if command -v lsof >/dev/null 2>&1; then
    stop_port api "$API_PORT"
    stop_port frontend "$FRONTEND_PORT"
fi

# 3) garante shutdown
sleep 1
for name in api frontend mcp; do
    pidfile="$PID_DIR/${name}.pid"
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile" 2>/dev/null || echo "")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
done

if [ "$killed_any" = "0" ]; then
    echo "Nenhum serviço em execução."
else
    echo "Serviços encerrados."
fi
