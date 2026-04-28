#!/usr/bin/env bash
# Inicializa todos os serviços do IA-Invest em paralelo:
#   - FastAPI backend  (http://localhost:${API_PORT:-8010})
#   - Next.js frontend (http://localhost:3000)
#   - MCP server       (stdin/stdout — útil só para debug local)
#
# Uso:
#   scripts/start.sh           # foreground: bloqueia o terminal, Ctrl+C derruba tudo
#   scripts/start.sh -d        # detached: roda em background; use `make stop`/`make logs`
#
# Logs em .dev-logs/<servico>.log, pids em .dev-logs/pids/<servico>.pid.

set -euo pipefail

DETACHED=0
while [ $# -gt 0 ]; do
    case "$1" in
        -d|--detach|--detached|--background)
            DETACHED=1
            shift
            ;;
        -h|--help)
            sed -n '2,11p' "$0"
            exit 0
            ;;
        *)
            echo "Opção desconhecida: $1" >&2
            exit 2
            ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8010}"
LOG_DIR="${IA_INVEST_DEV_LOG_DIR:-$ROOT/.dev-logs}"
PID_DIR="${IA_INVEST_DEV_PID_DIR:-$ROOT/.dev-logs/pids}"
mkdir -p "$LOG_DIR" "$PID_DIR"

# Flags opcionais via env
RUN_MCP="${RUN_MCP:-0}"           # MCP usa stdio; só ligue se quiser ver o processo de pé
RUN_FRONTEND="${RUN_FRONTEND:-1}"
RUN_API="${RUN_API:-1}"

pids=()

is_running() {
    local pidfile="$1"
    [ -f "$pidfile" ] || return 1
    local pid
    pid=$(cat "$pidfile" 2>/dev/null || echo "")
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_service() {
    local name="$1"
    shift
    local log="$LOG_DIR/${name}.log"
    local pidfile="$PID_DIR/${name}.pid"

    if is_running "$pidfile"; then
        echo "==> [$name] já em execução (pid=$(cat "$pidfile")). Pulando."
        return 0
    fi

    : > "$log"
    if [ "$DETACHED" = "1" ]; then
        # setsid desacopla do terminal; o processo sobrevive ao fim do script
        setsid "$@" >>"$log" 2>&1 < /dev/null &
        local pid=$!
        disown "$pid" 2>/dev/null || true
    else
        ( "$@" >>"$log" 2>&1 ) &
        local pid=$!
    fi
    pids+=("$pid")
    echo "$pid" > "$pidfile"
    echo "==> [$name] iniciado (pid=$pid) — log: $log"
}

cleanup() {
    echo ""
    echo "==> Encerrando serviços..."
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${pids[@]}"; do
        kill -9 "$pid" 2>/dev/null || true
    done
    rm -f "$PID_DIR"/*.pid 2>/dev/null || true
}

# Pré-checagens rápidas
if [ ! -f "ia_invest.db" ]; then
    echo "AVISO: ia_invest.db não encontrado. Rode 'make init' (ou 'make reset-db') antes." >&2
fi
if [ "$RUN_FRONTEND" = "1" ] && [ ! -d "frontend/node_modules" ]; then
    echo "AVISO: frontend/node_modules ausente. Rode 'make frontend-install' antes." >&2
fi

if [ "$RUN_API" = "1" ]; then
    start_service api uv run uvicorn mcp_server.http_api:app \
        --host 0.0.0.0 --port "$API_PORT" --reload
fi

if [ "$RUN_FRONTEND" = "1" ]; then
    start_service frontend bash -c 'cd frontend && npm run dev'
fi

if [ "$RUN_MCP" = "1" ]; then
    start_service mcp uv run python -m mcp_server.server
fi

echo ""
echo "Serviços de pé:"
[ "$RUN_API" = "1" ]      && echo "  - API:      http://localhost:$API_PORT (docs em /docs)"
[ "$RUN_FRONTEND" = "1" ] && echo "  - Frontend: http://localhost:3000"
[ "$RUN_MCP" = "1" ]      && echo "  - MCP:      stdio (log em $LOG_DIR/mcp.log)"
echo ""

if [ "$DETACHED" = "1" ]; then
    echo "Terminal livre. Comandos úteis:"
    echo "  make logs    # acompanhar"
    echo "  make stop    # encerrar todos"
    exit 0
fi

trap cleanup EXIT INT TERM
echo "Modo foreground — Ctrl+C encerra tudo."
echo "Acompanhe os logs:  tail -f $LOG_DIR/*.log"
echo ""
wait -n
echo "==> Um dos serviços terminou; derrubando os demais."
exit 1
