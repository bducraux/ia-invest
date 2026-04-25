"""MCP tool: ``get_position_with_quote`` — positions enriched with live prices.

Joins stored positions with the latest quotes resolved by
:class:`~mcp_server.services.quotes.MarketQuoteService` and delegates the
market-value / unrealised-P&L computation to
:class:`~domain.position_valuation_service.PositionValuationService`.

The tool intentionally keeps zero (and negative) quantity positions — these
are the historical-data-gap signal that :mod:`domain.position_service`
preserves, and silently dropping them would mask wallet inconsistencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.models import Position
from domain.position_valuation_service import PositionValuationService
from mcp_server.services.quotes import MarketQuoteService
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_position(row: dict[str, Any], portfolio_id: str) -> Position:
    return Position(
        portfolio_id=portfolio_id,
        asset_code=str(row["asset_code"]),
        asset_type=str(row["asset_type"]),
        asset_name=row.get("asset_name"),
        quantity=float(row.get("quantity", 0)),
        avg_price=int(row.get("avg_price", 0)),
        total_cost=int(row.get("total_cost", 0)),
        realized_pnl=int(row.get("realized_pnl", 0)),
        dividends=int(row.get("dividends", 0)),
        first_operation_date=row.get("first_operation_date"),
        last_operation_date=row.get("last_operation_date"),
    )


def get_position_with_quote(
    db: Database,
    portfolio_id: str,
    *,
    asset_code: str | None = None,
    quote_service: MarketQuoteService | None = None,
) -> dict[str, Any]:
    """Return positions for ``portfolio_id`` enriched with current quotes.

    Args:
        db: Open :class:`Database`.
        portfolio_id: Portfolio to load.
        asset_code: When provided, filters to a single asset (case-insensitive).
        quote_service: Optional pre-built quote service (used by tests). When
            omitted, a service is constructed against the DB connection with
            quotes disabled — this surfaces only cached prices, never hits
            the network from inside the MCP tool.
    """
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    pos_repo = PositionRepository(db.connection)
    rows = pos_repo.list_by_portfolio(portfolio_id)

    target_asset = asset_code.upper().strip() if asset_code else None
    if target_asset:
        rows = [r for r in rows if str(r["asset_code"]).upper() == target_asset]

    service = quote_service or MarketQuoteService(
        db.connection,
        enabled=False,
    )
    valuator = PositionValuationService()

    valued: list[dict[str, Any]] = []
    total_value: int = 0
    total_pnl: int = 0
    has_any_value = False

    for row in rows:
        position = _row_to_position(dict(row), portfolio_id)
        quote = service.resolve_price(position.asset_code, position.asset_type)
        valued_pos = valuator.value(position, quote)
        valued.append(valued_pos.to_dict())
        if valued_pos.current_value_cents is not None:
            total_value += valued_pos.current_value_cents
            has_any_value = True
        if valued_pos.unrealized_pnl_cents is not None:
            total_pnl += valued_pos.unrealized_pnl_cents

    payload: dict[str, Any] = {
        "portfolio_id": portfolio_id,
        "as_of": _utc_now_iso(),
        "positions": valued,
        "total_current_value_cents": total_value if has_any_value else None,
        "total_unrealized_pnl_cents": total_pnl if has_any_value else None,
    }
    return payload


__all__ = ["get_position_with_quote"]
