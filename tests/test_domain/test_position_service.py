"""Tests for PositionService."""

from __future__ import annotations

import pytest

from domain.position_service import PositionService


def _op(
    asset_code: str,
    operation_type: str,
    quantity: float,
    gross_value: int,
    fees: int = 0,
    date: str = "2024-01-01",
    idx: int = 1,
) -> dict[str, object]:
    return {
        "id": idx,
        "asset_code": asset_code,
        "asset_type": "stock",
        "asset_name": None,
        "operation_type": operation_type,
        "operation_date": date,
        "quantity": quantity,
        "gross_value": gross_value,
        "fees": fees,
    }


@pytest.fixture
def svc() -> PositionService:
    return PositionService()


def test_single_buy(svc: PositionService) -> None:
    ops = [_op("PETR4", "buy", 100, 350000, fees=150)]
    positions = svc.calculate(ops, "p1")
    assert len(positions) == 1
    pos = positions[0]
    assert pos.quantity == 100.0
    assert pos.total_cost == 350150
    assert pos.avg_price == 3502   # round(350150 / 100)
    assert pos.realized_pnl == 0


def test_buy_then_sell_all(svc: PositionService) -> None:
    ops = [
        _op("PETR4", "buy", 100, 350000, fees=150, date="2024-01-01", idx=1),
        _op("PETR4", "sell", 100, 400000, fees=200, date="2024-02-01", idx=2),
    ]
    positions = svc.calculate(ops, "p1")
    pos = positions[0]
    assert pos.quantity == 0.0
    # proceeds = 400000 - 200 = 399800
    # cost_sold = 350150
    # realized_pnl = 399800 - 350150 = 49650
    assert pos.realized_pnl == 49650


def test_partial_sell(svc: PositionService) -> None:
    ops = [
        _op("PETR4", "buy", 100, 350000, fees=0, date="2024-01-01", idx=1),
        _op("PETR4", "sell", 50, 175000, fees=0, date="2024-02-01", idx=2),
    ]
    positions = svc.calculate(ops, "p1")
    pos = positions[0]
    assert pos.quantity == 50.0
    assert pos.realized_pnl == 0  # sold at same price as bought


def test_dividend_accumulated(svc: PositionService) -> None:
    ops = [
        _op("PETR4", "buy", 100, 350000, idx=1),
        {**_op("PETR4", "dividend", 0, 5000, idx=2), "operation_type": "dividend"},
    ]
    positions = svc.calculate(ops, "p1")
    pos = positions[0]
    assert pos.dividends == 5000


def test_multiple_assets(svc: PositionService) -> None:
    ops = [
        _op("PETR4", "buy", 100, 350000, idx=1),
        _op("VALE3", "buy", 50, 400000, idx=2),
    ]
    positions = svc.calculate(ops, "p1")
    assert len(positions) == 2
    codes = {p.asset_code for p in positions}
    assert codes == {"PETR4", "VALE3"}


def test_idempotent(svc: PositionService) -> None:
    ops = [
        _op("PETR4", "buy", 100, 350000, idx=1),
        _op("PETR4", "sell", 50, 200000, idx=2),
    ]
    pos1 = svc.calculate(ops, "p1")
    pos2 = svc.calculate(ops, "p1")
    assert pos1[0].quantity == pos2[0].quantity
    assert pos1[0].realized_pnl == pos2[0].realized_pnl


def test_negative_intermediate_quantity_is_not_clamped(svc: PositionService) -> None:
    ops = [
        _op("USDT", "transfer_out", 300.3, 0, date="2022-01-01", idx=1),
        _op("USDT", "buy", 500.0, 250000, date="2022-01-02", idx=2),
    ]

    positions = svc.calculate(ops, "p1")
    pos = positions[0]

    # Arithmetic net must be preserved: -300.3 + 500 = 199.7
    assert pos.quantity == pytest.approx(199.7)


def test_sell_when_quantity_is_zero_does_not_corrupt_cost(svc: PositionService) -> None:
    # transfer_out before any buy leaves quantity negative.
    # A subsequent sell must still apply the quantity delta without crashing
    # and must not corrupt total_cost or realized_pnl.
    ops = [
        _op("BTC", "transfer_out", 0.1, 0, date="2021-01-01", idx=1),
        _op("BTC", "buy", 1.0, 50000_00, fees=100, date="2021-01-02", idx=2),
        _op("BTC", "sell", 0.5, 30000_00, fees=50, date="2021-01-03", idx=3),
    ]
    positions = svc.calculate(ops, "p1")
    pos = positions[0]

    # Net quantity: -0.1 + 1.0 - 0.5 = 0.4
    assert pos.quantity == pytest.approx(0.4)
    # total_cost and realized_pnl must be finite numbers, not NaN or negative-infinity
    assert pos.total_cost >= 0
    assert isinstance(pos.realized_pnl, int)


def test_partial_sell_avg_price_precision(svc: PositionService) -> None:
    # Buy 3 shares at 100.33 each (30099 cents total with fees).
    # Sell 1 share: cost_sold must be exactly round(30099 / 3) = 10033,
    # leaving total_cost = 20066 (not 20067 from double float rounding).
    ops = [
        _op("PETR4", "buy", 3, 30000, fees=99, date="2024-01-01", idx=1),
        _op("PETR4", "sell", 1, 11000, fees=0, date="2024-01-02", idx=2),
    ]
    positions = svc.calculate(ops, "p1")
    pos = positions[0]

    assert pos.quantity == 2.0
    # total_cost after sell = 30099 - round(30099/3 * 1) = 30099 - 10033 = 20066
    assert pos.total_cost == 20066
    assert pos.avg_price == round(20066 / 2)  # 10033
