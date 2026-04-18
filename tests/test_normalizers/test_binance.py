"""Tests for Binance operation normalizer."""

from __future__ import annotations

import pytest

from domain.fx_rates import FXRateCache
from normalizers.binance import BinanceOperationNormalizer


@pytest.fixture
def normalizer() -> BinanceOperationNormalizer:
    fx_cache = FXRateCache()
    return BinanceOperationNormalizer(fx_cache)


def test_normalize_brl_pair(normalizer: BinanceOperationNormalizer) -> None:
    """Test normalization of a BRL pair (no FX conversion needed)."""
    record = {
        "source": "binance_csv",
        "asset_code": "BTC",
        "operation_type": "buy",
        "operation_date": "2024-01-23",
        "quantity": "0.05181",
        "unit_price": "193100",
        "gross_value": "10004.511",
        "fees": "0",
        "pair": "BTCBRL",
        "quote_currency": "BRL",
    }
    operation = normalizer.normalize(record)

    assert operation.asset_code == "BTC"
    assert operation.operation_type == "buy"
    assert operation.quantity == pytest.approx(0.05181, rel=1e-5)
    # Gross value: 10004.511 BRL * 100 = 1000451.1 cents
    assert operation.gross_value == pytest.approx(1000451, abs=1)
    assert operation.fees == 0


def test_normalize_usdt_pair(normalizer: BinanceOperationNormalizer) -> None:
    """Test normalization of USDT pair with FX conversion."""
    record = {
        "source": "binance_csv",
        "asset_code": "USDT",
        "operation_type": "buy",
        "operation_date": "2026-04-13",
        "quantity": "989.8",
        "unit_price": "5.0007",
        "gross_value": "4949.69286",
        "fees": "0.9898",
        "pair": "USDTBRL",
        "quote_currency": "USDT",
        "fee_unit": "USDT",
    }
    operation = normalizer.normalize(record)

    assert operation.asset_code == "USDT"
    assert operation.operation_type == "buy"
    assert operation.quantity == pytest.approx(989.8, rel=1e-5)
    # Gross value: 4949.69286 USDT * 5.0007 (USDTBRL rate) = 24750.84 BRL ≈ 2475084 cents
    assert operation.gross_value == pytest.approx(2475084, rel=0.01)


def test_normalize_with_fee(normalizer: BinanceOperationNormalizer) -> None:
    """Test fee parsing and BRL conversion."""
    record = {
        "source": "binance_csv",
        "asset_code": "ETH",
        "operation_type": "buy",
        "operation_date": "2025-11-14",
        "quantity": "0.1519",
        "unit_price": "16474",
        "gross_value": "2502.4006",
        "fees": "0.0001519",
        "pair": "ETHBRL",
        "quote_currency": "BRL",
        "fee_unit": "ETH",
    }
    operation = normalizer.normalize(record)

    assert operation.asset_code == "ETH"
    assert operation.fees > 0  # Fee should be converted


def test_generate_deterministic_external_id(
    normalizer: BinanceOperationNormalizer,
) -> None:
    """Test that external_id is deterministic."""
    record = {
        "source": "binance_csv",
        "asset_code": "BTC",
        "operation_type": "buy",
        "operation_date": "2024-01-23",
        "quantity": "0.05181",
        "gross_value": "10004.511",
        "pair": "BTCBRL",
    }

    id1 = normalizer._generate_external_id(record)
    id2 = normalizer._generate_external_id(record)

    assert id1 == id2
    assert len(id1) == 16


def test_external_id_differs_per_trade(normalizer: BinanceOperationNormalizer) -> None:
    """Test that different trades have different external_ids."""
    record1 = {
        "source": "binance_csv",
        "asset_code": "BTC",
        "operation_type": "buy",
        "operation_date": "2024-01-23",
        "quantity": "0.05181",
        "gross_value": "10004.511",
    }
    record2 = {
        "source": "binance_csv",
        "asset_code": "BTC",
        "operation_type": "buy",
        "operation_date": "2024-01-24",  # Different date
        "quantity": "0.05181",
        "gross_value": "10004.511",
    }

    id1 = normalizer._generate_external_id(record1)
    id2 = normalizer._generate_external_id(record2)

    assert id1 != id2
