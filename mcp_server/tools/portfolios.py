"""MCP server tools — portfolio management."""

from __future__ import annotations

from typing import Any

from storage.repository.db import Database
from storage.repository.import_jobs import ImportJobRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def list_portfolios(db: Database) -> list[dict[str, Any]]:
    """Return all active portfolios with basic metadata."""
    repo = PortfolioRepository(db.connection)
    portfolios = repo.list_active()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "base_currency": p.base_currency,
            "status": p.status,
        }
        for p in portfolios
    ]


def get_portfolio_summary(db: Database, portfolio_id: str) -> dict[str, Any]:
    """Return a summary of a portfolio: positions count, total cost, realised P&L."""
    portfolio_repo = PortfolioRepository(db.connection)
    portfolio = portfolio_repo.get(portfolio_id)
    if portfolio is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    pos_repo = PositionRepository(db.connection)
    positions = pos_repo.list_open_by_portfolio(portfolio_id)

    total_cost = sum(p["total_cost"] for p in positions)
    realized_pnl = sum(p["realized_pnl"] for p in positions)
    dividends = sum(p["dividends"] for p in positions)
    open_positions = len(positions)

    job_repo = ImportJobRepository(db.connection)
    recent_jobs = job_repo.list_by_portfolio(portfolio_id, limit=5)

    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "open_positions": open_positions,
        "total_cost_cents": total_cost,
        "realized_pnl_cents": realized_pnl,
        "dividends_cents": dividends,
        "recent_imports": [
            {
                "id": j["id"],
                "file_name": j["file_name"],
                "status": j["status"],
                "valid_records": j["valid_records"],
                "created_at": j["created_at"],
            }
            for j in recent_jobs
        ],
    }


def get_portfolio_positions(
    db: Database,
    portfolio_id: str,
    *,
    open_only: bool = True,
) -> list[dict[str, Any]]:
    """Return positions for a portfolio.

    Args:
        open_only: If True (default), return only positions with quantity > 0.
    """
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return [{"error": f"Portfolio '{portfolio_id}' not found."}]

    pos_repo = PositionRepository(db.connection)
    if open_only:
        return pos_repo.list_open_by_portfolio(portfolio_id)
    return pos_repo.list_by_portfolio(portfolio_id)


def get_portfolio_operations(
    db: Database,
    portfolio_id: str,
    *,
    asset_code: str | None = None,
    operation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return operations for a portfolio, optionally filtered."""
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return [{"error": f"Portfolio '{portfolio_id}' not found."}]

    op_repo = OperationRepository(db.connection)
    return op_repo.list_by_portfolio(
        portfolio_id,
        asset_code=asset_code,
        operation_type=operation_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def compare_portfolios(db: Database, portfolio_ids: list[str]) -> list[dict[str, Any]]:
    """Return a side-by-side summary for multiple portfolios."""
    result = []
    for pid in portfolio_ids:
        summary = get_portfolio_summary(db, pid)
        result.append(summary)
    return result


def get_consolidated_summary(db: Database) -> dict[str, Any]:
    """Return a consolidated view across all active portfolios."""
    portfolios = list_portfolios(db)
    if not portfolios:
        return {"portfolios": [], "totals": {}}

    summaries = []
    total_cost = 0
    total_pnl = 0
    total_dividends = 0
    total_positions = 0

    for p in portfolios:
        summary = get_portfolio_summary(db, p["id"])
        summaries.append(summary)
        total_cost += summary.get("total_cost_cents", 0)
        total_pnl += summary.get("realized_pnl_cents", 0)
        total_dividends += summary.get("dividends_cents", 0)
        total_positions += summary.get("open_positions", 0)

    return {
        "portfolios": summaries,
        "totals": {
            "open_positions": total_positions,
            "total_cost_cents": total_cost,
            "realized_pnl_cents": total_pnl,
            "dividends_cents": total_dividends,
        },
    }
