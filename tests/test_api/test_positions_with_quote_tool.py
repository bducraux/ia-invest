"""Tests for the ``get_position_with_quote`` MCP tool."""

from __future__ import annotations

from typing import Any

from domain.models import Portfolio, Position
from mcp_server.tools.positions_with_quote import get_position_with_quote
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


class _StubQuoteService:
    """Mimics ``MarketQuoteService.resolve_price`` for tests."""

    def __init__(self, table: dict[str, dict[str, Any] | None]) -> None:
        self._table = table
        self.calls: list[tuple[str, str]] = []

    def resolve_price(
        self, asset_code: str, asset_type: str
    ) -> dict[str, Any] | None:
        self.calls.append((asset_code, asset_type))
        return self._table.get(asset_code.upper())


def _seed(db: Database, portfolio_id: str, positions: list[Position]) -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=portfolio_id, name=portfolio_id, base_currency="BRL")
    )
    PositionRepository(db.connection).upsert_many(positions)


def _pos(
    portfolio_id: str,
    asset_code: str,
    *,
    quantity: float = 100.0,
    avg_price: int = 1000,
    total_cost: int = 100_000,
    asset_type: str = "stock",
) -> Position:
    return Position(
        portfolio_id=portfolio_id,
        asset_code=asset_code,
        asset_type=asset_type,
        asset_name=asset_code,
        quantity=quantity,
        avg_price=avg_price,
        total_cost=total_cost,
    )


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    result = get_position_with_quote(tmp_db, "ghost")
    assert "error" in result
    assert "ghost" in result["error"]


def test_returns_positions_with_quotes_when_available(tmp_db: Database) -> None:
    _seed(
        tmp_db,
        "renda-variavel",
        [
            _pos("renda-variavel", "ITSA4", quantity=1000, avg_price=850, total_cost=850_000),
            _pos("renda-variavel", "BBAS3", quantity=200, avg_price=2500, total_cost=500_000),
        ],
    )
    quotes = _StubQuoteService(
        {
            "ITSA4": {"price_cents": 920, "source": "brapi", "age_seconds": 60, "status": "live"},
            "BBAS3": {"price_cents": 2800, "source": "brapi", "age_seconds": 60, "status": "live"},
        }
    )

    result = get_position_with_quote(
        tmp_db, "renda-variavel", quote_service=quotes  # type: ignore[arg-type]
    )

    assert result["portfolio_id"] == "renda-variavel"
    assert result["as_of"].endswith("Z")

    positions = {p["asset_code"]: p for p in result["positions"]}
    assert positions["ITSA4"]["current_value_cents"] == 920_000
    assert positions["ITSA4"]["unrealized_pnl_cents"] == 70_000
    assert positions["BBAS3"]["current_value_cents"] == 560_000
    assert positions["BBAS3"]["unrealized_pnl_cents"] == 60_000

    assert result["total_current_value_cents"] == 920_000 + 560_000
    assert result["total_unrealized_pnl_cents"] == 70_000 + 60_000


def test_position_without_quote_keeps_position_with_null_quote_fields(
    tmp_db: Database,
) -> None:
    _seed(
        tmp_db,
        "renda-variavel",
        [_pos("renda-variavel", "ITSA4")],
    )
    quotes = _StubQuoteService({})  # No quotes at all.

    result = get_position_with_quote(
        tmp_db, "renda-variavel", quote_service=quotes  # type: ignore[arg-type]
    )
    assert len(result["positions"]) == 1
    p = result["positions"][0]
    assert p["asset_code"] == "ITSA4"
    assert p["current_price_cents"] is None
    assert p["current_value_cents"] is None
    assert p["unrealized_pnl_cents"] is None

    # When no quote is available for any position, totals collapse to None.
    assert result["total_current_value_cents"] is None
    assert result["total_unrealized_pnl_cents"] is None


def test_filter_by_asset_code_is_case_insensitive(tmp_db: Database) -> None:
    _seed(
        tmp_db,
        "renda-variavel",
        [
            _pos("renda-variavel", "ITSA4"),
            _pos("renda-variavel", "BBAS3"),
        ],
    )
    quotes = _StubQuoteService(
        {"ITSA4": {"price_cents": 920, "source": "brapi", "age_seconds": 0, "status": "live"}}
    )

    result = get_position_with_quote(
        tmp_db,
        "renda-variavel",
        asset_code="itsa4",
        quote_service=quotes,  # type: ignore[arg-type]
    )

    assert len(result["positions"]) == 1
    assert result["positions"][0]["asset_code"] == "ITSA4"
    # Quote service should only have been queried for the filtered asset.
    assert quotes.calls == [("ITSA4", "stock")]


def test_zero_and_negative_quantity_positions_are_preserved(tmp_db: Database) -> None:
    """Historical-data-gap signal must not be silently dropped."""
    _seed(
        tmp_db,
        "cripto",
        [
            _pos("cripto", "BTC", quantity=0.0, avg_price=0, total_cost=0, asset_type="crypto"),
            _pos(
                "cripto",
                "ETH",
                quantity=-5.0,
                avg_price=1_000_000,
                total_cost=-5_000_000,
                asset_type="crypto",
            ),
        ],
    )
    quotes = _StubQuoteService(
        {
            "BTC": {"price_cents": 30_000_000, "source": "binance", "age_seconds": 0, "status": "live"},
            "ETH": {"price_cents": 1_500_000, "source": "binance", "age_seconds": 0, "status": "live"},
        }
    )

    result = get_position_with_quote(
        tmp_db, "cripto", quote_service=quotes  # type: ignore[arg-type]
    )
    assets = {p["asset_code"]: p for p in result["positions"]}

    # Zero-quantity is preserved (not filtered out).
    assert "BTC" in assets
    assert assets["BTC"]["current_value_cents"] == 0
    # Negative balance: -5 * 1_500_000 = -7_500_000 cents market value.
    assert assets["ETH"]["quantity"] == "-5.0"
    assert assets["ETH"]["current_value_cents"] == -7_500_000
