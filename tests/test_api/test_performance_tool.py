"""Tests for the ``get_portfolio_performance`` MCP tool."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.models import Operation, Portfolio, Position
from mcp_server.tools.performance import get_portfolio_performance
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
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


def _seed(db: Database, pid: str = "renda-variavel") -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name=pid, base_currency="BRL")
    )


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    assert "error" in get_portfolio_performance(tmp_db, "ghost")


def test_returns_error_for_invalid_window(tmp_db: Database) -> None:
    _seed(tmp_db)
    assert "error" in get_portfolio_performance(tmp_db, "renda-variavel", period_months=0)


def test_lifetime_metrics_with_dividends_and_quotes(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid)
    PositionRepository(tmp_db.connection).upsert(
        Position(
            portfolio_id=pid,
            asset_code="ITSA4",
            asset_type="stock",
            quantity=1000,
            avg_price=850,
            total_cost=850_000,
            dividends=20_000,
        )
    )
    OperationRepository(tmp_db.connection).insert_many(
        [
            Operation(
                portfolio_id=pid, source="t", external_id="d1",
                asset_code="ITSA4", asset_type="stock",
                operation_type="dividend", operation_date="2025-09-15",
                quantity=0, unit_price=0, gross_value=20_000,
            ),
        ]
    )

    result = get_portfolio_performance(
        tmp_db,
        pid,
        period_months=12,
        today=date(2026, 4, 25),
        quote_service=_StubQuotes({"ITSA4": 920}),  # type: ignore[arg-type]
    )
    t = result["totals"]
    assert t["total_cost_cents"] == 850_000
    assert t["current_value_cents"] == 920_000
    assert t["unrealized_pnl_cents"] == 70_000
    assert t["lifetime_dividends_cents"] == 20_000
    # 70_000 + 20_000 = 90_000 over 850_000 = 0.1059
    assert t["lifetime_total_return_pct"] == 0.1059
    assert result["period"]["dividends_received_cents"] == 20_000
    # No CDI series populated → block is null.
    assert result["period"]["cdi_accumulated_pct"] is None


def test_period_uses_cdi_series_when_cache_covers_window(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid)
    # Seed CDI cache covering the full 12-month window (with a buffer
    # before period_start so coverage_min is unambiguously <= start).
    repo = BenchmarkRatesRepository(tmp_db.connection)
    rows = []
    cur = date(2025, 4, 1)
    end = date(2026, 4, 30)
    while cur <= end:
        if cur.weekday() < 5:
            rows.append((cur, Decimal("0.0005")))
        cur = date.fromordinal(cur.toordinal() + 1)
    repo.upsert_many("CDI", rows)

    result = get_portfolio_performance(
        tmp_db, pid, period_months=12, today=date(2026, 4, 25)
    )
    p = result["period"]
    assert p["cdi_accumulated_pct"] is not None
    assert p["cdi_business_days"] > 0
    # No partial-series warning.
    assert all(w["code"] != "cdi_partial_series" for w in result["warnings"])


def test_partial_cdi_series_emits_warning(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid)
    BenchmarkRatesRepository(tmp_db.connection).upsert_many(
        "CDI",
        [(date(2025, 9, 1), Decimal("0.0005"))],  # one row in the middle
    )
    result = get_portfolio_performance(
        tmp_db, pid, period_months=12, today=date(2026, 4, 25)
    )
    codes = {w["code"] for w in result["warnings"]}
    assert "cdi_partial_series" in codes
