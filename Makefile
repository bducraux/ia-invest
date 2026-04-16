.PHONY: help install init create-portfolio import-all lint type-check test clean server

help:
	@echo "IA-Invest - Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make install              Install dependencies (uv sync --extra dev)"
	@echo ""
	@echo "Database:"
	@echo "  make init                 Initialize database"
	@echo ""
	@echo "Portfolios:"
	@echo "  make create-portfolio     Create a new portfolio (interactive)"
	@echo "  make import-all           Import all active portfolios"
	@echo ""
	@echo "Server:"
	@echo "  make server               Start MCP server"
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

create-portfolio:
	uv run python scripts/create_portfolio.py

import-all:
	uv run python scripts/import_all.py

server:
	uv run python -m mcp_server.server

lint:
	uv run ruff check .

type-check:
	uv run mypy .

test:
	uv run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -f .coverage
