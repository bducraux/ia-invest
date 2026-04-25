"""Unit tests for ``domain.position_valuation_service``."""

from __future__ import annotations

from domain.models import Position
from domain.position_valuation_service import PositionValuationService, ValuedPosition


def _make_position(
    *,
    quantity: float = 1000.0,
    avg_price: int = 850,
    total_cost: int = 850_000,
    asset_code: str = "ITSA4",
) -> Position:
    return Position(
        portfolio_id="renda-variavel",
        asset_code=asset_code,
        asset_type="stock",
        asset_name=asset_code,
        quantity=quantity,
        avg_price=avg_price,
        total_cost=total_cost,
    )


def test_value_with_quote_computes_market_value_and_pnl() -> None:
    # Concrete known-good case (matches the prompt example):
    # 1000 shares @ R$8.50 cost, current price R$9.20 → MV R$9200, P&L +R$700 (+8.24%).
    pos = _make_position(quantity=1000, avg_price=850, total_cost=850_000)
    quote = {
        "price_cents": 920,
        "source": "brapi",
        "age_seconds": 120,
        "status": "cache_fresh",
        "fetched_at": "2026-04-25T14:28:00Z",
    }

    result = PositionValuationService().value(pos, quote)

    assert isinstance(result, ValuedPosition)
    assert result.current_price_cents == 920
    assert result.current_value_cents == 920_000
    assert result.unrealized_pnl_cents == 70_000
    assert result.unrealized_pnl_pct == 0.0824

    # Provenance is preserved verbatim.
    assert result.quote_source == "brapi"
    assert result.quote_age_seconds == 120
    assert result.quote_status == "cache_fresh"
    assert result.quote_fetched_at == "2026-04-25T14:28:00Z"

    # All monetary fields are integers (cents).
    assert isinstance(result.current_price_cents, int)
    assert isinstance(result.current_value_cents, int)
    assert isinstance(result.unrealized_pnl_cents, int)
    assert isinstance(result.avg_price_cents, int)
    assert isinstance(result.total_cost_cents, int)


def test_value_with_no_quote_preserves_position_and_nulls_quote_fields() -> None:
    pos = _make_position()
    result = PositionValuationService().value(pos, None)

    assert result.asset_code == "ITSA4"
    assert result.quantity == 1000.0
    assert result.avg_price_cents == 850
    assert result.total_cost_cents == 850_000

    assert result.current_price_cents is None
    assert result.current_value_cents is None
    assert result.unrealized_pnl_cents is None
    assert result.unrealized_pnl_pct is None


def test_value_with_quote_payload_missing_price_returns_null_quote_fields() -> None:
    # MarketQuoteService returns a dict without ``price_cents`` only when the
    # response is degenerate; the service should treat this as "no quote".
    pos = _make_position()
    quote = {"source": "stale", "status": "cache_stale"}
    result = PositionValuationService().value(pos, quote)  # type: ignore[arg-type]

    assert result.current_price_cents is None
    assert result.current_value_cents is None
    assert result.unrealized_pnl_cents is None
    assert result.quote_source == "stale"
    assert result.quote_status == "cache_stale"


def test_value_with_zero_quantity_yields_zero_market_value() -> None:
    # Sold-everything case: quantity=0, total_cost=0.
    pos = _make_position(quantity=0.0, avg_price=0, total_cost=0)
    quote = {"price_cents": 920, "source": "brapi"}
    result = PositionValuationService().value(pos, quote)

    assert result.current_value_cents == 0
    # No cost basis → percent is undefined and surfaced as None (not NaN/0).
    assert result.unrealized_pnl_cents == 0
    assert result.unrealized_pnl_pct is None


def test_value_preserves_negative_quantity_no_clamp() -> None:
    # Historical-data-gap scenario from WALLET_MODEL.md: quantity is negative
    # because sells were imported before the matching buys. We must NOT clamp
    # to zero — the negative balance is the diagnostic signal.
    pos = _make_position(quantity=-50.0, avg_price=850, total_cost=-42_500)
    quote = {"price_cents": 920, "source": "brapi"}

    result = PositionValuationService().value(pos, quote)

    assert result.quantity == -50.0
    assert result.current_value_cents == -46_000  # -50 * 920
    # Cost basis stored as -42500; market value -46000 → P&L = -46000 - (-42500) = -3500.
    assert result.unrealized_pnl_cents == -3_500


def test_value_with_fractional_crypto_quantity_uses_decimal_arithmetic() -> None:
    # 0.12345678 BTC at R$300,000 → 0.12345678 * 30_000_000 cents = 3_703_703.4
    # → rounds half-even to 3_703_703 cents.
    pos = Position(
        portfolio_id="cripto",
        asset_code="BTC",
        asset_type="crypto",
        quantity=0.12345678,
        avg_price=20_000_000,  # R$200,000.00 per BTC cost
        total_cost=2_469_136,  # 0.12345678 * 20_000_000
    )
    quote = {"price_cents": 30_000_000, "source": "binance"}

    result = PositionValuationService().value(pos, quote)
    assert result.current_value_cents == 3_703_703
    # Quantity must round-trip through to_dict as a string preserving precision.
    assert "0.12345678" in result.to_dict()["quantity"]


def test_to_dict_emits_serialisable_primitive_types() -> None:
    pos = _make_position()
    quote = {
        "price_cents": 920,
        "source": "brapi",
        "age_seconds": 0,
        "status": "live",
        "fetched_at": None,
    }
    out = PositionValuationService().value(pos, quote).to_dict()

    assert isinstance(out["asset_code"], str)
    assert isinstance(out["quantity"], str)
    assert isinstance(out["avg_price_cents"], int)
    assert isinstance(out["current_value_cents"], int)
    assert isinstance(out["unrealized_pnl_cents"], int)
    assert isinstance(out["unrealized_pnl_pct"], float)
