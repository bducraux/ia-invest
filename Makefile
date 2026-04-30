.PHONY: help install init migrate reset-db clear-cache create-portfolio adjust-balance check-balance import-all portfolio-overview lint type-check test clean server api-server start stop logs frontend-install frontend-dev frontend-build frontend-test frontend-lint sync-historical-prices sync-historical-prices-full

API_PORT ?= 8010

help:
	@echo "IA-Invest - Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make install              Install dependencies (uv sync --extra dev)"
	@echo ""
	@echo "Database:"
	@echo "  make init                 Initialize database (fresh schema)"
	@echo "  make migrate              Apply pending migrations to an existing database"
	@echo "  make reset-db             Delete + reinit DB, import all portfolios, sync CDI from BACEN"
	@echo "  make clear-cache          Delete extraction caches (portfolios/*/.cache/)"
	@echo ""
	@echo "Portfolios:"
	@echo "  make create-portfolio     Create a new portfolio (interactive)"
	@echo "  make check-balance        Check balances for one or more assets"
	@echo "                            Example: make check-balance ARGS=\"--portfolio cripto --assets BTC,ETH\""
	@echo "  make adjust-balance       Run manual asset balance adjustment script"
	@echo "                            Example: make adjust-balance ARGS=\"--portfolio cripto --asset BTC --real-quantity 0.55076538 --dry-run\""
	@echo "  make portfolio-overview   Show a full overview of all assets in a portfolio"
	@echo "                            Example: make portfolio-overview ARGS=\"--portfolio cripto --sort cost --hide-zero\""
	@echo "  make import-all           Import all active portfolios"
	@echo ""
	@echo "Server:"
	@echo "  make server               Start MCP server"
	@echo "  make api-server           Start FastAPI backend (http://localhost:8010)"
	@echo "                            Example: make api-server API_PORT=8010"
	@echo "  make start                Sobe API + frontend juntos (Ctrl+C derruba todos)"
	@echo "                            Vars opcionais: API_PORT, RUN_MCP=1, RUN_FRONTEND=0, RUN_API=0"
	@echo "  make stop                 Para todos os serviços iniciados pelo make start"
	@echo "  make logs                 Acompanha em tempo real os logs em .dev-logs/"
	@echo ""
	@echo "Frontend:"
	@echo "  make frontend-install     Install frontend dependencies (npm ci)"
	@echo "  make frontend-dev         Start frontend dev server (http://localhost:3000)"
	@echo "  make frontend-build       Build frontend for production"
	@echo "  make frontend-test        Run frontend Vitest tests"
	@echo "  make frontend-lint        Run frontend ESLint"
	@echo ""
	@echo "Development:"
	@echo "  make lint                 Run ruff linter"
	@echo "  make type-check           Run mypy type checker"
	@echo "  make test                 Run pytest tests"
	@echo "  make clean                Remove generated artifacts"
	@echo ""

install:
	uv sync --extra dev

init:
	uv run python scripts/init_db.py

migrate:
	uv run python scripts/migrate.py

reset-db:
	rm -f ia_invest.db ia_invest.db-wal ia_invest.db-shm
	uv run python scripts/init_db.py
	@echo ""
	@echo "Bootstrapping members from portfolios/ folder layout..."
	uv run python scripts/bootstrap_members_from_fs.py
	@for dir in portfolios/*/*/processed; do \
		if ls "$$dir"/* 2>/dev/null | grep -qv '.gitkeep'; then \
			cp "$$dir"/* "$$(dirname $$dir)/inbox/" 2>/dev/null || true; \
		fi; \
	done
	uv run python scripts/import_all.py --verbose
	@echo ""
	@echo "Bootstrapping CDI historical series from BACEN..."
	@uv run python scripts/sync_benchmark_rates.py --benchmark CDI --full || \
		echo "WARNING: CDI sync failed (offline?). Run 'make sync-cdi-full' later."
	@echo ""
	@echo "Bootstrapping USDBRL PTAX historical series from BACEN..."
	@uv run python scripts/sync_fx_rates.py --pair USDBRL --full || \
		echo "WARNING: USDBRL sync failed (offline?). Run 'make sync-fx-full' later."
	@echo ""
	@echo "Bootstrapping monthly historical prices (Yahoo) for every asset..."
	@uv run python scripts/sync_historical_prices.py --full || \
		echo "WARNING: historical prices sync failed (offline?). Run 'make sync-historical-prices-full' later."

create-portfolio:
	uv run python scripts/create_portfolio.py

check-balance:
	uv run python scripts/check_asset_balance.py $(ARGS)

adjust-balance:
	uv run python scripts/adjust_asset_balance.py $(ARGS)

portfolio-overview:
	uv run python scripts/portfolio_overview.py $(ARGS)

import-all:
	uv run python scripts/import_all.py

clear-cache:
	@count=$$(find portfolios -type d -name .cache 2>/dev/null | wc -l); \
	if [ "$$count" -eq 0 ]; then \
		echo "No extraction caches found."; \
	else \
		size=$$(du -sh portfolios/*/.cache 2>/dev/null | awk '{s+=$$1} END {print s"K (approx)"}'); \
		find portfolios -type d -name .cache -exec rm -rf {} +; \
		echo "Removed $$count extraction cache director(ies)."; \
	fi

server:
	uv run python -m mcp_server.server

api-server:
	uv run uvicorn mcp_server.http_api:app --host 0.0.0.0 --port $(API_PORT) --reload

start:
	@API_PORT=$(API_PORT) bash scripts/start.sh -d

stop:
	@API_PORT=$(API_PORT) bash scripts/stop.sh

logs:
	@mkdir -p .dev-logs
	@if ls .dev-logs/*.log >/dev/null 2>&1; then \
		tail -n 50 -F .dev-logs/*.log; \
	else \
		echo "Nenhum log em .dev-logs/. Rode 'make start' primeiro."; \
	fi

sync-cdi:
	uv run python scripts/sync_benchmark_rates.py --benchmark CDI $(ARGS)

sync-cdi-full:
	uv run python scripts/sync_benchmark_rates.py --benchmark CDI --full

sync-fx:
	uv run python scripts/sync_fx_rates.py $(ARGS)

sync-fx-full:
	uv run python scripts/sync_fx_rates.py --full

sync-historical-prices:
	uv run python scripts/sync_historical_prices.py $(ARGS)

sync-historical-prices-full:
	uv run python scripts/sync_historical_prices.py --full

frontend-install:
	cd frontend && npm ci

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm run test

frontend-lint:
	cd frontend && npm run lint

lint:
	uv run ruff check .

type-check:
	uv run mypy .

test:
	uv run pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -f .coverage
