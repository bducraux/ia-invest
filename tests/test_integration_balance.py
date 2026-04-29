"""Integration regressions for crypto balance reconciliation.

These tests cover end-to-end flow:
raw extractor-like records -> normalizer -> operation repository -> position service.
"""

from __future__ import annotations

from collections import defaultdict

from domain.position_service import PositionService
from normalizers.operations import OperationNormalizer
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository

_BUY_TYPES = {"buy", "transfer_in", "split_bonus"}
_SELL_TYPES = {"sell", "transfer_out"}


def _operation_net_by_asset(operations: list[dict[str, object]]) -> dict[str, float]:
    net: dict[str, float] = defaultdict(float)
    for op in operations:
        code = str(op["asset_code"])
        qty = float(op["quantity"])
        op_type = str(op["operation_type"])
        if op_type in _BUY_TYPES:
            net[code] += qty
        elif op_type in _SELL_TYPES:
            net[code] -= qty
    return dict(net)


def _position_qty_by_asset(positions: list[dict[str, object]]) -> dict[str, float]:
    return {str(pos["asset_code"]): float(pos["quantity"]) for pos in positions}


def test_integration_quote_legs_keep_usdt_consistent(tmp_db, sample_portfolio) -> None:
    # Buy USDT with BRL, then spend and receive USDT via BTCUSDT trades.
    raw_records = [
        {
            "source": "binance_csv",
            "external_id": "e1",
            "asset_code": "USDT",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-01",
            "quantity": "1000",
            "unit_price": "5",
            "gross_value": "5000",
            "fees": "1",
            "quote_currency": "BRL",
            "fee_unit": "USDT",
        },
        {
            "source": "binance_csv",
            "external_id": "e2",
            "asset_code": "BTC",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-02",
            "quantity": "0.005",
            "unit_price": "60000",
            "gross_value": "300",
            "fees": "0.3",
            "quote_currency": "USDT",
            "fee_unit": "USDT",
        },
        {
            "source": "binance_csv",
            "external_id": "e3",
            "asset_code": "BTC",
            "asset_type": "crypto",
            "operation_type": "sell",
            "operation_date": "2022-01-03",
            "quantity": "0.001",
            "unit_price": "70000",
            "gross_value": "70",
            "fees": "0.07",
            "quote_currency": "USDT",
            "fee_unit": "USDT",
        },
    ]

    PortfolioRepository(tmp_db.connection).upsert(sample_portfolio)

    normalizer = OperationNormalizer()
    norm = normalizer.normalize(raw_records, sample_portfolio.id)
    assert norm.errors == []

    op_repo = OperationRepository(tmp_db.connection)
    inserted, skipped = op_repo.insert_many(norm.valid)
    assert inserted == len(norm.valid)
    assert skipped == 0

    all_ops = op_repo.list_all_by_portfolio(sample_portfolio.id)
    positions = PositionService().calculate(all_ops, sample_portfolio.id)
    PositionRepository(tmp_db.connection).upsert_many(positions)

    net_ops = _operation_net_by_asset(all_ops)
    net_pos = _position_qty_by_asset(
        PositionRepository(tmp_db.connection).list_by_portfolio(sample_portfolio.id)
    )

    assert net_ops["USDT"] == 769.63
    assert net_ops["BTC"] == 0.004
    assert net_pos["USDT"] == net_ops["USDT"]
    assert net_pos["BTC"] == net_ops["BTC"]


def test_integration_preserves_negative_intermediate_balance(tmp_db, sample_portfolio) -> None:
    # Historical gap case: spend USDT before the corresponding USDT buy appears.
    # Final balance must be arithmetic net, not clamped to zero at any step.
    raw_records = [
        {
            "source": "binance_csv",
            "external_id": "n1",
            "asset_code": "BTC",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-01",
            "quantity": "0.005",
            "unit_price": "60000",
            "gross_value": "300",
            "fees": "0.3",
            "quote_currency": "USDT",
            "fee_unit": "USDT",
        },
        {
            "source": "binance_csv",
            "external_id": "n2",
            "asset_code": "USDT",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-02",
            "quantity": "500",
            "unit_price": "5",
            "gross_value": "2500",
            "fees": "0",
            "quote_currency": "BRL",
            "fee_unit": "USDT",
        },
    ]

    PortfolioRepository(tmp_db.connection).upsert(sample_portfolio)

    norm = OperationNormalizer().normalize(raw_records, sample_portfolio.id)
    assert norm.errors == []

    op_repo = OperationRepository(tmp_db.connection)
    op_repo.insert_many(norm.valid)

    all_ops = op_repo.list_all_by_portfolio(sample_portfolio.id)
    positions = PositionService().calculate(all_ops, sample_portfolio.id)
    PositionRepository(tmp_db.connection).upsert_many(positions)

    net_ops = _operation_net_by_asset(all_ops)
    net_pos = _position_qty_by_asset(
        PositionRepository(tmp_db.connection).list_by_portfolio(sample_portfolio.id)
    )

    # 500 buy - 300.3 spent in quote leg.
    assert net_ops["USDT"] == 199.7
    assert net_pos["USDT"] == 199.7


def test_integration_non_fiat_quote_pair_updates_quote_asset(tmp_db, sample_portfolio) -> None:
    # ETHBTC should deduct BTC via quote leg, otherwise BTC gets inflated.
    raw_records = [
        {
            "source": "binance_csv",
            "external_id": "b1",
            "asset_code": "BTC",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-01",
            "quantity": "0.1000",
            "unit_price": "200000",
            "gross_value": "20000",
            "fees": "0",
            "quote_currency": "BRL",
            "fee_unit": "BTC",
        },
        {
            "source": "binance_csv",
            "external_id": "b2",
            "asset_code": "ETH",
            "asset_type": "crypto",
            "operation_type": "buy",
            "operation_date": "2022-01-02",
            "quantity": "1",
            "unit_price": "0.05",
            "gross_value": "0.05",
            "fees": "0.0005",
            "quote_currency": "BTC",
            "fee_unit": "BTC",
        },
    ]

    PortfolioRepository(tmp_db.connection).upsert(sample_portfolio)

    norm = OperationNormalizer().normalize(raw_records, sample_portfolio.id)
    assert norm.errors == []

    op_repo = OperationRepository(tmp_db.connection)
    op_repo.insert_many(norm.valid)

    all_ops = op_repo.list_all_by_portfolio(sample_portfolio.id)
    positions = PositionService().calculate(all_ops, sample_portfolio.id)
    PositionRepository(tmp_db.connection).upsert_many(positions)

    net_ops = _operation_net_by_asset(all_ops)
    net_pos = _position_qty_by_asset(
        PositionRepository(tmp_db.connection).list_by_portfolio(sample_portfolio.id)
    )

    assert net_ops["BTC"] == 0.0495
    assert net_ops["ETH"] == 1.0
    assert net_pos["BTC"] == net_ops["BTC"]
    assert net_pos["ETH"] == net_ops["ETH"]
