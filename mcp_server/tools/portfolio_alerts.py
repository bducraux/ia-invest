"""MCP tool: ``get_portfolio_alerts`` — unified portfolio alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.portfolio_alerts_service import PortfolioAlertsService
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.concentration import get_concentration_analysis
from mcp_server.tools.fixed_income_summary import get_fixed_income_summary
from mcp_server.tools.positions_with_quote import get_position_with_quote
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_portfolio_alerts(
    db: Database,
    portfolio_id: str,
    *,
    quote_service: MarketQuoteService | None = None,
) -> dict[str, Any]:
    """Aggregate concentration, fixed-income and quote alerts.

    The tool reuses the read-only sub-tools so each alert source remains
    a single source of truth. Sub-tool errors (missing portfolio) are
    propagated unchanged.
    """
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    quotes = quote_service or MarketQuoteService(db.connection, enabled=False)

    concentration = get_concentration_analysis(db, portfolio_id, quote_service=quotes)
    fixed_income = get_fixed_income_summary(db, portfolio_id)
    positions = get_position_with_quote(db, portfolio_id, quote_service=quotes)

    missing_assets: list[str] = []
    for pos in positions.get("positions", []):
        # Only flag positions still held; historical-data-gap rows
        # (quantity <= 0) are reported by other tools, not as alerts.
        try:
            qty = float(pos.get("quantity", 0))
        except (TypeError, ValueError):
            qty = 0.0
        if qty > 0 and pos.get("current_price_cents") is None:
            missing_assets.append(str(pos.get("asset_code", "")))

    payload = PortfolioAlertsService().aggregate(
        concentration_alerts=concentration.get("alerts", []),
        upcoming_maturities=fixed_income.get("upcoming_maturities", []),
        missing_quote_assets=missing_assets,
        incomplete_fixed_income_valuations=fixed_income.get("incomplete_valuations", []),
    )
    payload["portfolio_id"] = portfolio_id
    payload["as_of"] = _utc_now_iso()
    return payload


__all__ = ["get_portfolio_alerts"]
