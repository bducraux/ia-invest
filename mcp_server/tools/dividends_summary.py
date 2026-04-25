"""MCP tool: ``get_dividends_summary`` — proventos breakdown over a window."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from domain.dividends_service import PROVENT_TYPES, DividendsService
from domain.position_valuation_service import PositionValuationService
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.positions_with_quote import _row_to_position
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _portfolio_market_value_cents(
    db: Database,
    portfolio_id: str,
    quote_service: MarketQuoteService,
) -> int | None:
    """Sum the market value of every open position via the cached quotes.

    Returns ``None`` when no position has a usable quote — the DY estimate
    is then omitted to avoid presenting a misleading figure.
    """
    pos_repo = PositionRepository(db.connection)
    valuator = PositionValuationService()
    total = 0
    has_value = False
    for row in pos_repo.list_by_portfolio(portfolio_id):
        position = _row_to_position(dict(row), portfolio_id)
        if position.quantity <= 0:
            continue
        quote = quote_service.resolve_price(position.asset_code, position.asset_type)
        valued = valuator.value(position, quote)
        if valued.current_value_cents is not None:
            total += valued.current_value_cents
            has_value = True
    return total if has_value else None


def get_dividends_summary(
    db: Database,
    portfolio_id: str,
    *,
    period_months: int = 12,
    today: date | None = None,
    quote_service: MarketQuoteService | None = None,
) -> dict[str, Any]:
    """Return the dividend/JCP/rendimento summary for the given window.

    Args:
        db: Open database.
        portfolio_id: Portfolio to load.
        period_months: Window size in months (must be >= 1).
        today: Optional override for the window's end date — useful in
            tests for deterministic boundaries.
        quote_service: Pre-built quote service (tests). When omitted, an
            offline-mode service is used so the call only consumes cached
            prices and never blocks on the network.
    """
    if period_months < 1:
        return {"error": "period_months must be >= 1"}

    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    end = today or datetime.now(UTC).date()
    start = end - relativedelta(months=period_months) + relativedelta(days=1)

    op_repo = OperationRepository(db.connection)
    rows: list[dict[str, Any]] = []
    for op_type in sorted(PROVENT_TYPES):
        rows.extend(
            op_repo.list_all_by_portfolio(
                portfolio_id,
                operation_type=op_type,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        )

    service = quote_service or MarketQuoteService(db.connection, enabled=False)
    portfolio_value = _portfolio_market_value_cents(db, portfolio_id, service)

    summary = DividendsService().summarise(
        rows,
        period_start=start,
        period_end=end,
        portfolio_value_cents=portfolio_value,
    )
    summary["portfolio_id"] = portfolio_id
    summary["as_of"] = _utc_now_iso()
    return summary


__all__ = ["get_dividends_summary"]
