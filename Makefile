.PHONY: help install init reset-db create-portfolio adjust-balance check-balance import-all portfolio-overview lint type-check test clean server frontend-install frontend-dev frontend-build frontend-test frontend-lint

help:
	@echo "IA-Invest - Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make install              Install dependencies (uv sync --extra dev)"
	@echo ""
	@echo "Database:"
	@echo "  make init                 Initialize database"
	@echo "  make reset-db             Delete and reinitialize database, then import all portfolios"
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

reset-db:
	rm -f ia_invest.db
	uv run python scripts/init_db.py
	@for dir in portfolios/*/processed; do \
		if ls "$$dir"/* 2>/dev/null | grep -qv '.gitkeep'; then \
			cp "$$dir"/* "$$(dirname $$dir)/inbox/" 2>/dev/null || true; \
		fi; \
	done
	uv run python scripts/import_all.py

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

server:
	uv run python -m mcp_server.server

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
