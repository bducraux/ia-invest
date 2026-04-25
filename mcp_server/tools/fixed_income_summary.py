"""MCP tool: ``get_fixed_income_summary`` — CDB/LCI/LCA portfolio overview."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from domain.fixed_income_rates import (
    DailyRateProvider,
    FlatCDIRateProvider,
    SQLiteDailyRateProvider,
)
from domain.fixed_income_summary_service import (
    FixedIncomeSummaryService,
    ValuedFixedIncomePosition,
)
from domain.fixed_income_valuation import FixedClock, FixedIncomeValuationService
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.portfolios import PortfolioRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_provider(db: Database) -> DailyRateProvider:
    """Return the best available CDI provider for valuation.

    Falls back to a flat zero-rate provider when the BACEN cache is empty
    so positions still surface (with ``is_complete=False`` and a warning)
    instead of crashing the tool. Tests inject their own providers.
    """
    repo = BenchmarkRatesRepository(db.connection)
    _, _, count = repo.get_coverage("CDI")
    if count > 0:
        return SQLiteDailyRateProvider(repo)
    return FlatCDIRateProvider(0)


def get_fixed_income_summary(
    db: Database,
    portfolio_id: str,
    *,
    as_of: date | None = None,
    cdi_provider: DailyRateProvider | None = None,
) -> dict[str, Any]:
    """Return the fixed-income summary payload for ``portfolio_id``.

    Args:
        db: Open database.
        portfolio_id: Portfolio to load.
        as_of: Optional valuation date override (used in tests for a stable
            maturity ladder). Defaults to ``today`` in UTC.
        cdi_provider: Optional CDI series override. When omitted the tool
            uses the SQLite cache when populated, otherwise a zero-rate
            fallback so the call never crashes.
    """
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    valuation_date = as_of or datetime.now(UTC).date()
    provider = cdi_provider or _build_provider(db)
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(valuation_date),
    )

    repo = FixedIncomePositionRepository(db.connection)
    valued: list[ValuedFixedIncomePosition] = []
    for position in repo.list_by_portfolio(portfolio_id):
        valuation = service.revalue_as_of(position, valuation_date)
        valued.append(ValuedFixedIncomePosition(position=position, valuation=valuation))

    payload = FixedIncomeSummaryService().summarise(valued, as_of=valuation_date)
    payload["portfolio_id"] = portfolio_id
    payload["generated_at"] = _utc_now_iso()
    return payload


__all__ = ["get_fixed_income_summary"]
