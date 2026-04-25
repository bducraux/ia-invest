"""Tests for the ``get_portfolio_alerts`` MCP tool."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import FlatCDIRateProvider
from domain.models import Portfolio, Position
from mcp_server.tools.portfolio_alerts import get_portfolio_alerts
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


class _StubQuotes:
    def __init__(self, prices: dict[str, int]) -> None:
        self._prices = prices

    def resolve_price(self, asset_code: str, asset_type: str) -> dict[str, int] | None:
        if asset_code.upper() in self._prices:
            return {
                "price_cents": self._prices[asset_code.upper()],
                "source": "stub", "age_seconds": 0, "status": "live",
            }
        return None


def _seed(db: Database, pid: str) -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name=pid, base_currency="BRL")
    )


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    assert "error" in get_portfolio_alerts(tmp_db, "ghost")


def test_empty_portfolio_returns_low_diversification_only(tmp_db: Database) -> None:
    _seed(tmp_db, "renda-variavel")
    result = get_portfolio_alerts(tmp_db, "renda-variavel")
    assert result["total"] >= 1
    codes = {a["code"] for a in result["alerts"]}
    assert "low_diversification" in codes


def test_aggregates_concentration_and_missing_quote(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid)
    PositionRepository(tmp_db.connection).upsert_many(
        [
            Position(
                portfolio_id=pid, asset_code="ITSA4", asset_type="stock",
                quantity=1000, avg_price=850, total_cost=850_000,
            ),
            Position(
                portfolio_id=pid, asset_code="XPTO3", asset_type="stock",
                quantity=100, avg_price=500, total_cost=50_000,
            ),
        ]
    )
    quotes = _StubQuotes({"ITSA4": 1000})  # XPTO3 has no quote.

    result = get_portfolio_alerts(tmp_db, pid, quote_service=quotes)  # type: ignore[arg-type]

    sources = {a["source"] for a in result["alerts"]}
    assert "concentration" in sources
    assert "quotes" in sources
    quote_alert = next(a for a in result["alerts"] if a["source"] == "quotes")
    assert quote_alert["details"]["assets"] == ["XPTO3"]


def test_includes_upcoming_fixed_income_maturity(tmp_db: Database) -> None:
    pid = "renda-fixa"
    _seed(tmp_db, pid)
    FixedIncomePositionRepository(tmp_db.connection).insert(
        FixedIncomePosition(
            portfolio_id=pid,
            institution="Banco X",
            asset_type="CDB",
            product_name="CDB Curto",
            remuneration_type="PRE",
            benchmark="NONE",
            investor_type="PF",
            currency="BRL",
            application_date="2025-04-25",
            maturity_date=date.today().isoformat(),  # vencendo hoje
            principal_applied_brl=100_000,
            fixed_rate_annual_percent=13.0,
        )
    )
    # Use a flat-zero CDI provider so PRE valuation doesn't need the cache.
    # (PRE doesn't use CDI but the provider is built when the cache is empty.)
    _ = FlatCDIRateProvider(Decimal("0"))

    result = get_portfolio_alerts(tmp_db, pid)
    fi_alerts = [a for a in result["alerts"] if a["source"] == "fixed_income"]
    assert any(a["code"] == "upcoming_maturity" for a in fi_alerts)


def test_alerts_sorted_by_severity(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid)
    # Single asset → critical concentration alert.
    PositionRepository(tmp_db.connection).upsert(
        Position(
            portfolio_id=pid, asset_code="ITSA4", asset_type="stock",
            quantity=1000, avg_price=850, total_cost=850_000,
        )
    )
    result = get_portfolio_alerts(
        tmp_db, pid, quote_service=_StubQuotes({"ITSA4": 1000}),  # type: ignore[arg-type]
    )
    levels = [a["level"] for a in result["alerts"]]
    rank = {"critical": 0, "warning": 1, "info": 2}
    assert levels == sorted(levels, key=lambda lv: rank.get(lv, 99))
