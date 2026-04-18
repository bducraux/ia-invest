"""Tests for BinanceSimpleEarnExtractor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from extractors.binance_simple_earn import BinanceSimpleEarnExtractor, _normalize_date


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_EARN_ROWS = """\
Tempo,Moeda,Quantidade,Tipo
26-04-15 00:29:21,USDT,0.016438,Bonus Tiered APR Rewards
26-04-15 00:23:35,BNB,0.00000328,Bonus Tiered APR Rewards
2026-04-14,ENA,0.00131552,Real-time APR Rewards
2026-04-14,BTC,0.00000049,Real-time APR Rewards
20-05-08 21:42:27,XLM,0.05,Rewards
20-05-08 21:41:54,ADA,0,Rewards
"""

SIMPLE_EARN_ZERO_QTY = """\
Tempo,Moeda,Quantidade,Tipo
20-05-08 21:42:27,XLM,0,Rewards
20-05-08 21:41:54,ADA,0,Rewards
"""


@pytest.fixture
def simple_earn_csv(tmp_path: Path) -> Path:
    f = tmp_path / "simple_earn.csv"
    f.write_text(SIMPLE_EARN_ROWS, encoding="utf-8")
    return f


@pytest.fixture
def zero_qty_csv(tmp_path: Path) -> Path:
    f = tmp_path / "zero_qty.csv"
    f.write_text(SIMPLE_EARN_ZERO_QTY, encoding="utf-8")
    return f


@pytest.fixture
def extractor() -> BinanceSimpleEarnExtractor:
    return BinanceSimpleEarnExtractor()


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------


def test_can_handle_simple_earn_file(extractor, simple_earn_csv):
    assert extractor.can_handle(simple_earn_csv) is True


def test_cannot_handle_binance_trade_csv(extractor, tmp_path):
    f = tmp_path / "trades.csv"
    f.write_text("Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n")
    assert extractor.can_handle(f) is False


def test_cannot_handle_binance_trade_csv_pt(extractor, tmp_path):
    f = tmp_path / "trades_pt.csv"
    f.write_text("Tempo,Par,Lado,Preço,Executado,Quantidade,Taxa\n")
    assert extractor.can_handle(f) is False


def test_cannot_handle_random_csv(extractor, tmp_path):
    f = tmp_path / "other.csv"
    f.write_text("Date,Amount,Value\n2026-01-01,1.0,100.0\n")
    assert extractor.can_handle(f) is False


# ---------------------------------------------------------------------------
# extract — record counts and zero-qty filtering
# ---------------------------------------------------------------------------


def test_extract_record_count(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    # 5 data rows, 1 has qty=0 → 5 records expected
    assert len(result.records) == 5


def test_extract_skips_zero_quantity(extractor, zero_qty_csv):
    result = extractor.extract(zero_qty_csv)
    assert len(result.records) == 0
    assert len(result.errors) == 0


# ---------------------------------------------------------------------------
# Zero-cost domain rule
# ---------------------------------------------------------------------------


def test_records_have_zero_cost(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        assert rec["unit_price"] == "0"
        assert rec["gross_value"] == "0"
        assert rec["fees"] == "0"


def test_records_use_split_bonus_type(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        assert rec["operation_type"] == "split_bonus"


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def test_asset_code_uppercase(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    assets = {r["asset_code"] for r in result.records}
    assert assets == {"USDT", "BNB", "ENA", "BTC", "XLM"}


def test_asset_type_is_crypto(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        assert rec["asset_type"] == "crypto"


def test_broker_is_binance(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        assert rec["broker"] == "binance"


def test_source_type(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    assert result.source_type == "binance_simple_earn"
    for rec in result.records:
        assert rec["source"] == "binance_simple_earn"


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("26-04-15 00:29:21", "2026-04-15"),
        ("20-05-08 21:42:27", "2020-05-08"),
        ("2026-04-14", "2026-04-14"),
        ("2020-05-08", "2020-05-08"),
    ],
)
def test_normalize_date(raw, expected):
    assert _normalize_date(raw) == expected


def test_dates_normalised_in_records(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        date = rec["operation_date"]
        assert len(date) == 10
        assert date[4] == "-" and date[7] == "-"


# ---------------------------------------------------------------------------
# Deterministic external_id
# ---------------------------------------------------------------------------


def test_external_id_is_deterministic(extractor, simple_earn_csv):
    r1 = extractor.extract(simple_earn_csv)
    r2 = extractor.extract(simple_earn_csv)
    ids1 = [r["external_id"] for r in r1.records]
    ids2 = [r["external_id"] for r in r2.records]
    assert ids1 == ids2


def test_external_ids_are_unique(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    ids = [r["external_id"] for r in result.records]
    assert len(ids) == len(set(ids))


def test_external_id_length(extractor, simple_earn_csv):
    result = extractor.extract(simple_earn_csv)
    for rec in result.records:
        assert len(rec["external_id"]) == 16


# ---------------------------------------------------------------------------
# Position integration: zero-cost rewards reduce avg_price
# ---------------------------------------------------------------------------


def test_zero_cost_reward_reduces_avg_price():
    """Buying 1 BTC at R$500,000 then earning 0.1 BTC as reward should
    reduce avg_price from 500,000 to ~454,545 (total_cost stays the same)."""
    from domain.position_service import PositionService

    svc = PositionService()

    buy_op = {
        "id": 1,
        "asset_code": "BTC",
        "asset_type": "crypto",
        "asset_name": None,
        "operation_type": "buy",
        "operation_date": "2026-01-01",
        "quantity": 1.0,
        "unit_price": 50_000_000,   # R$500,000 in cents
        "gross_value": 50_000_000,  # R$500,000 in cents
        "fees": 0,
    }

    reward_op = {
        "id": 2,
        "asset_code": "BTC",
        "asset_type": "crypto",
        "asset_name": None,
        "operation_type": "split_bonus",
        "operation_date": "2026-01-15",
        "quantity": 0.1,
        "unit_price": 0,
        "gross_value": 0,
        "fees": 0,
    }

    positions = svc.calculate([buy_op, reward_op], portfolio_id="test")
    btc = next(p for p in positions if p.asset_code == "BTC")

    # total_cost should be unchanged (only the buy contributed)
    assert btc.total_cost == buy_op["gross_value"] + buy_op["fees"]
    # quantity increased by reward
    assert btc.quantity == pytest.approx(1.1)
    # avg_price must be LOWER than original unit price
    assert btc.avg_price < buy_op["unit_price"]
