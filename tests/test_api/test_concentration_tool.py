"""Tests for the ``get_concentration_analysis`` MCP tool."""

from __future__ import annotations

from domain.models import Portfolio, Position
from mcp_server.tools.concentration import get_concentration_analysis
from storage.repository.db import Database
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


def _seed(db: Database, pid: str, positions: list[Position]) -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name=pid, base_currency="BRL")
    )
    PositionRepository(db.connection).upsert_many(positions)


def _pos(
    pid: str,
    code: str,
    *,
    quantity: float = 100.0,
    avg_price: int = 1000,
    total_cost: int = 100_000,
) -> Position:
    return Position(
        portfolio_id=pid,
        asset_code=code,
        asset_type="stock",
        quantity=quantity,
        avg_price=avg_price,
        total_cost=total_cost,
    )


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    result = get_concentration_analysis(tmp_db, "ghost")
    assert "error" in result


def test_uses_market_quotes_when_available(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(
        tmp_db,
        pid,
        [
            _pos(pid, "ITSA4", quantity=1000, avg_price=850, total_cost=850_000),
            _pos(pid, "BBAS3", quantity=500, avg_price=2000, total_cost=1_000_000),
        ],
    )
    quotes = _StubQuotes({"ITSA4": 1000, "BBAS3": 1000})  # MV: 1_000_000 + 500_000 = 1_500_000

    result = get_concentration_analysis(tmp_db, pid, quote_service=quotes)  # type: ignore[arg-type]

    assert result["portfolio_id"] == pid
    assert result["total_value_cents"] == 1_500_000
    by_asset = {a["asset_code"]: a for a in result["by_asset"]}
    assert by_asset["ITSA4"]["value_cents"] == 1_000_000
    assert by_asset["BBAS3"]["value_cents"] == 500_000
    assert "valuation_warnings" not in result


def test_falls_back_to_cost_basis_when_quote_missing(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(
        tmp_db,
        pid,
        [
            _pos(pid, "ITSA4", quantity=1000, avg_price=850, total_cost=850_000),
            _pos(pid, "XPTO3", quantity=100, avg_price=500, total_cost=50_000),
        ],
    )
    quotes = _StubQuotes({"ITSA4": 1000})

    result = get_concentration_analysis(tmp_db, pid, quote_service=quotes)  # type: ignore[arg-type]

    assert result["total_value_cents"] == 1_000_000 + 50_000  # XPTO3 falls back to cost
    warnings = result["valuation_warnings"]
    assert warnings["assets"] == ["XPTO3"]


def test_skips_zero_and_negative_quantity_positions(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(
        tmp_db,
        pid,
        [
            _pos(pid, "ITSA4", quantity=1000, avg_price=850, total_cost=850_000),
            _pos(pid, "BBAS3", quantity=0, avg_price=0, total_cost=0),
            _pos(pid, "VALE3", quantity=-50, avg_price=1000, total_cost=-50_000),
        ],
    )
    quotes = _StubQuotes({"ITSA4": 1000, "VALE3": 1000})

    result = get_concentration_analysis(tmp_db, pid, quote_service=quotes)  # type: ignore[arg-type]
    assert result["num_assets"] == 1
    assert {a["asset_code"] for a in result["by_asset"]} == {"ITSA4"}


def test_empty_portfolio_returns_low_diversification_alert(tmp_db: Database) -> None:
    pid = "renda-variavel"
    _seed(tmp_db, pid, [])
    result = get_concentration_analysis(tmp_db, pid)
    assert result["num_assets"] == 0
    codes = {a["code"] for a in result["alerts"]}
    assert "low_diversification" in codes
    assert result["as_of"].endswith("Z")
