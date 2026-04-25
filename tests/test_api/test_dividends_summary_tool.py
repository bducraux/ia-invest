"""Tests for the ``get_dividends_summary`` MCP tool."""

from __future__ import annotations

from datetime import date

from domain.models import Operation, Portfolio, Position
from mcp_server.tools.dividends_summary import get_dividends_summary
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
                "source": "stub",
                "age_seconds": 0,
                "status": "live",
            }
        return None


def _seed_portfolio(db: Database, pid: str = "renda-variavel") -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name=pid, base_currency="BRL")
    )


def _add_provent(
    db: Database,
    pid: str,
    *,
    asset_code: str,
    op_date: str,
    amount: int,
    op_type: str = "dividend",
    external_id: str | None = None,
) -> None:
    op = Operation(
        portfolio_id=pid,
        source="test",
        external_id=external_id or f"{asset_code}-{op_date}-{op_type}",
        asset_code=asset_code,
        asset_type="stock",
        operation_type=op_type,
        operation_date=op_date,
        quantity=0,
        unit_price=0,
        gross_value=amount,
    )
    OperationRepository(db.connection).insert_many([op])


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    result = get_dividends_summary(tmp_db, "ghost")
    assert "error" in result and "ghost" in result["error"]


def test_returns_error_for_invalid_window(tmp_db: Database) -> None:
    _seed_portfolio(tmp_db)
    result = get_dividends_summary(tmp_db, "renda-variavel", period_months=0)
    assert "error" in result


def test_summary_aggregates_proventos_in_window(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed_portfolio(tmp_db, pid)
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2025-08-15", amount=20_000)
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2025-11-15", amount=18_000, op_type="jcp")
    _add_provent(tmp_db, pid, asset_code="HGLG11", op_date="2025-10-15", amount=5_000, op_type="rendimento")
    # Out-of-window provento is ignored.
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2024-01-01", amount=99_999)

    result = get_dividends_summary(
        tmp_db,
        pid,
        period_months=12,
        today=date(2026, 4, 25),
    )

    assert result["portfolio_id"] == pid
    assert result["totals"]["total_received_cents"] == 43_000
    assert result["totals"]["events_count"] == 3
    assert result["by_type"]["dividend_cents"] == 20_000
    assert result["by_type"]["jcp_cents"] == 18_000
    assert result["by_type"]["rendimento_cents"] == 5_000
    # No portfolio positions → DY estimate omitted.
    assert result["portfolio_dy_estimate"] is None


def test_summary_includes_dy_estimate_when_positions_have_quotes(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed_portfolio(tmp_db, pid)
    PositionRepository(tmp_db.connection).upsert(
        Position(
            portfolio_id=pid,
            asset_code="ITSA4",
            asset_type="stock",
            quantity=1000,
            avg_price=850,
            total_cost=850_000,
        )
    )
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2025-09-15", amount=100_000)

    result = get_dividends_summary(
        tmp_db,
        pid,
        period_months=12,
        today=date(2026, 4, 25),
        quote_service=_StubQuotes({"ITSA4": 1000}),  # market value 1000*1000 = 1_000_000c
    )
    dy = result["portfolio_dy_estimate"]
    assert dy is not None
    assert dy["portfolio_value_cents"] == 1_000_000
    assert dy["value"] == 0.1


def test_summary_handles_portfolio_without_proventos(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed_portfolio(tmp_db, pid)
    result = get_dividends_summary(
        tmp_db, pid, period_months=12, today=date(2026, 4, 25)
    )
    assert result["totals"]["total_received_cents"] == 0
    assert result["by_asset"] == []


def test_summary_supports_custom_window_size(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed_portfolio(tmp_db, pid)
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2024-08-15", amount=15_000)
    _add_provent(tmp_db, pid, asset_code="ITSA4", op_date="2025-08-15", amount=20_000)

    result = get_dividends_summary(
        tmp_db, pid, period_months=24, today=date(2026, 4, 25)
    )
    assert result["period"]["months"] == 24
    assert result["totals"]["total_received_cents"] == 35_000
