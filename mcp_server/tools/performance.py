"""MCP tool: ``get_portfolio_performance`` — lifetime + period performance."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from domain.dividends_service import PROVENT_TYPES
from domain.performance_service import (
    CdiAccumulation,
    PortfolioPerformanceService,
    compound_cdi,
)
from domain.position_valuation_service import PositionValuationService, ValuedPosition
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.positions_with_quote import _row_to_position
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _value_positions(
    db: Database,
    portfolio_id: str,
    quote_service: MarketQuoteService,
) -> tuple[list[ValuedPosition], int, int]:
    """Return (valued_positions, lifetime_dividends_cents, lifetime_realized_pnl_cents)."""
    pos_repo = PositionRepository(db.connection)
    valuator = PositionValuationService()
    valued: list[ValuedPosition] = []
    lifetime_div = 0
    lifetime_realized_pnl = 0
    for row in pos_repo.list_by_portfolio(portfolio_id):
        row_dict = dict(row)
        position = _row_to_position(row_dict, portfolio_id)
        # Lifetime dividends/realized PnL are summed across *all* positions
        # (including those without a quote), so they survive a missing quote.
        if position.quantity > 0:
            lifetime_div += int(row_dict.get("dividends", 0) or 0)
            lifetime_realized_pnl += int(row_dict.get("realized_pnl", 0) or 0)
        quote = quote_service.resolve_price(position.asset_code, position.asset_type)
        valued.append(valuator.value(position, quote))
    return valued, lifetime_div, lifetime_realized_pnl


def _build_cdi_block(
    db: Database, period_start: date, period_end: date
) -> CdiAccumulation | None:
    """Compound the CDI daily series across the window.

    Returns ``None`` when the cache has no rows at all (silent — also
    surfaced by the ``warnings`` list when partial). Coverage is judged
    "complete" when BACEN's stored range fully spans the requested window.
    """
    repo = BenchmarkRatesRepository(db.connection)
    coverage_min, coverage_max, count = repo.get_coverage("CDI")
    if count == 0 or coverage_min is None or coverage_max is None:
        return None
    rates = repo.get_range("CDI", period_start, period_end)
    accumulation = compound_cdi(rates)
    # Window fully covered iff the BACEN cache extends to both bounds.
    complete = coverage_min <= period_start and coverage_max >= period_end
    if complete:
        return accumulation
    return CdiAccumulation(
        accumulated_pct=accumulation.accumulated_pct,
        business_days=accumulation.business_days,
        coverage_complete=False,
        missing_days=0,
    )


def get_portfolio_performance(
    db: Database,
    portfolio_id: str,
    *,
    period_months: int = 12,
    today: date | None = None,
    quote_service: MarketQuoteService | None = None,
) -> dict[str, Any]:
    """Lifetime + period performance metrics for ``portfolio_id``.

    ``period_months`` controls only the dividend window and the CDI
    accumulation. Lifetime metrics use the position table as-is (no time
    slicing — IA-Invest does not store historical valuation snapshots).
    """
    if period_months < 1:
        return {"error": "period_months must be >= 1"}

    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    end = today or datetime.now(UTC).date()
    start = end - relativedelta(months=period_months) + relativedelta(days=1)

    quotes = quote_service or MarketQuoteService(db.connection, enabled=False)
    valued, lifetime_div, lifetime_realized_pnl = _value_positions(db, portfolio_id, quotes)

    op_repo = OperationRepository(db.connection)
    period_dividends = 0
    for op_type in sorted(PROVENT_TYPES):
        for row in op_repo.list_all_by_portfolio(
            portfolio_id,
            operation_type=op_type,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        ):
            try:
                period_dividends += int(row.get("gross_value") or row.get("net_value") or 0)
            except (TypeError, ValueError):
                continue

    cdi = _build_cdi_block(db, start, end)

    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        valued,
        lifetime_dividends_cents=lifetime_div,
        period_dividends_cents=period_dividends,
        period_months=period_months,
        period_start=start,
        period_end=end,
        cdi=cdi,
        lifetime_realized_pnl_cents=lifetime_realized_pnl,
    )
    payload["portfolio_id"] = portfolio_id
    payload["as_of"] = _utc_now_iso()
    return payload


__all__ = ["get_portfolio_performance"]
