"""Tests for BinanceCsvExtractor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from extractors.binance_csv import BinanceCsvExtractor, _parse_base_asset


@pytest.fixture
def extractor() -> BinanceCsvExtractor:
    return BinanceCsvExtractor()


@pytest.fixture
def binance_csv_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        Date(UTC),Pair,Side,Price,Executed,Amount,Fee
        2023-06-01 10:00:00,BTCUSDT,BUY,27500.00,0.1 BTC,2750.00,0.0001 BTC
        2023-06-15 14:30:00,ETHUSDT,SELL,1800.00,0.5 ETH,900.00,0.00025 ETH
        2023-07-01 08:00:00,BNBBRL,BUY,350.00,2 BNB,700.00,0.002 BNB
    """)
    f = tmp_path / "binance_trades.csv"
    f.write_text(content, encoding="utf-8")
    return f


def test_can_handle_binance_csv(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    assert extractor.can_handle(binance_csv_file) is True


def test_cannot_handle_generic_csv(
    extractor: BinanceCsvExtractor, tmp_path: Path
) -> None:
    generic = tmp_path / "data.csv"
    generic.write_text("date,value\n2024-01-01,100\n", encoding="utf-8")
    assert extractor.can_handle(generic) is False


def test_extract_record_count(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    result = extractor.extract(binance_csv_file)
    assert len(result.records) == 3
    assert not result.has_errors


def test_extract_asset_code(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    result = extractor.extract(binance_csv_file)
    assert result.records[0]["asset_code"] == "BTC"
    assert result.records[1]["asset_code"] == "ETH"
    assert result.records[2]["asset_code"] == "BNB"


def test_extract_operation_types(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    result = extractor.extract(binance_csv_file)
    assert result.records[0]["operation_type"] == "buy"
    assert result.records[1]["operation_type"] == "sell"


def test_extract_operation_date_format(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    result = extractor.extract(binance_csv_file)
    assert result.records[0]["operation_date"] == "2023-06-01"


def test_extract_asset_type_is_crypto(
    extractor: BinanceCsvExtractor, binance_csv_file: Path
) -> None:
    result = extractor.extract(binance_csv_file)
    for record in result.records:
        assert record["asset_type"] == "crypto"


@pytest.mark.parametrize(
    "pair,expected",
    [
        ("BTCUSDT", "BTC"),
        ("ETHBRL", "ETH"),
        ("BNBBUSD", "BNB"),
        ("SOLUSDT", "SOL"),
        ("DOTBTC", "DOT"),
        ("UNKNOWN", "UNKNOWN"),
    ],
)
def test_parse_base_asset(pair: str, expected: str) -> None:
    assert _parse_base_asset(pair) == expected
