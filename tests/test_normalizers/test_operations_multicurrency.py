"""Tests for multi-currency normalization in OperationNormalizer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from normalizers.operations import OperationNormalizer


@dataclass
class _StubResolved:
    pair: str
    rate_date: date
    rate: Decimal
    source: str


class _StubFxService:
    def __init__(self, rate: Decimal = Decimal("5.0")) -> None:
        self._rate = rate
        self.calls: list[tuple[str, str]] = []

    def get_rate_for_trade(self, pair: str, trade_date):  # noqa: ANN001
        self.calls.append((pair, str(trade_date)))
        return _StubResolved(
            pair=pair,
            rate_date=date(2024, 5, 21),
            rate=self._rate,
            source="bacen_ptax",
        )


def _raw_buy_usd(**overrides):
    base = {
        "source": "avenue_csv",
        "broker": "Avenue",
        "trade_currency": "USD",
        "operation_type": "buy",
        "operation_date": "2024-05-19",
        "settlement_date": "2024-05-21",
        "asset_code": "AAPL",
        "asset_type": "stock_us",
        "quantity": 0.10,
        "unit_price": 200.00,
        "gross_value": 20.00,
        "fees": 0,
    }
    base.update(overrides)
    return base


def test_usd_buy_converts_to_brl_using_settlement_date_rate() -> None:
    fx = _StubFxService(rate=Decimal("5.20"))
    norm = OperationNormalizer(fx_service=fx)
    result = norm.normalize([_raw_buy_usd()], portfolio_id="p1")

    assert not result.errors
    assert len(result.valid) == 1
    op = result.valid[0]

    # Native USD values (cents)
    assert op.unit_price_native == 20_000  # USD 200.00
    assert op.gross_value_native == 2_000  # USD 20.00
    assert op.trade_currency == "USD"
    assert op.fx_rate_at_trade == "5.20"
    assert op.fx_rate_source == "bacen_ptax"

    # Converted BRL values
    assert op.unit_price == 104_000  # 20000 * 5.20
    assert op.gross_value == 10_400   # 2000 * 5.20

    # FX lookup used settlement_date
    assert fx.calls == [("USDBRL", "2024-05-21")]


def test_brl_buy_passes_through_unchanged() -> None:
    norm = OperationNormalizer(fx_service=None)
    raw = {
        "source": "broker_csv",
        "trade_currency": "BRL",
        "operation_type": "buy",
        "operation_date": "2024-05-19",
        "asset_code": "PETR4",
        "asset_type": "stock",
        "quantity": 100,
        "unit_price": 30.00,
        "gross_value": 3000.00,
    }
    result = norm.normalize([raw], portfolio_id="p1")
    assert not result.errors
    op = result.valid[0]
    assert op.trade_currency == "BRL"
    assert op.unit_price == 3000  # 30.00 in cents
    assert op.unit_price_native == 3000
    assert op.fx_rate_at_trade == "1"
    assert op.fx_rate_source == "native_brl"


def test_unsupported_row_rejected_with_reason() -> None:
    norm = OperationNormalizer(fx_service=_StubFxService())
    raw = {"_unsupported": True, "_unsupported_reason": "Avenue line not recognised"}
    result = norm.normalize([raw], portfolio_id="p1")
    assert len(result.valid) == 0
    assert len(result.errors) == 1
    assert "unsupported_operation" in result.errors[0].message


def test_usd_trade_without_fx_service_raises() -> None:
    norm = OperationNormalizer(fx_service=None)
    result = norm.normalize([_raw_buy_usd()], portfolio_id="p1")
    assert len(result.valid) == 0
    assert len(result.errors) == 1
    assert "USD" in result.errors[0].message
