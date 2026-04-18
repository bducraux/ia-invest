"""Tests for BinanceCsvExtractor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from extractors.binance_csv import BinanceCsvExtractor, _parse_base_asset, _normalize_date


@pytest.fixture
def extractor() -> BinanceCsvExtractor:
    return BinanceCsvExtractor()


@pytest.fixture
def binance_csv_file_english(tmp_path: Path) -> Path:
    """English format (YYYY-MM-DD)."""
    content = textwrap.dedent("""\
        Date(UTC),Pair,Side,Price,Executed,Amount,Fee
        2023-06-01 10:00:00,BTCUSDT,BUY,27500.00,0.1 BTC,2750.00,0.0001 BTC
        2023-06-15 14:30:00,ETHUSDT,SELL,1800.00,0.5 ETH,900.00,0.00025 ETH
        2023-07-01 08:00:00,BNBBRL,BUY,350.00,2 BNB,700.00,0.002 BNB
    """)
    f = tmp_path / "binance_trades_en.csv"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def binance_csv_file_portuguese(tmp_path: Path) -> Path:
    """Portuguese format (yy-mm-dd)."""
    content = textwrap.dedent("""\
        Tempo,Par,Lado,Preço,Executado,Quantidade,Taxa
        26-04-13 21:13:14,USDTBRL,BUY,5.0007,989.8USDT,4949.69286BRL,0.9898USDT
        26-02-17 08:08:13,BTCBRL,BUY,354647,0.0028BTC,993.0116BRL,0.0000028BTC
        26-02-17 08:08:13,BTCBRL,BUY,354647,0.00002BTC,7.09294BRL,0.00000002BTC
    """)
    f = tmp_path / "binance_trades_pt.csv"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def binance_csv_split_fills(tmp_path: Path) -> Path:
    """Portuguese format with split fills (same time + pair + side)."""
    content = textwrap.dedent("""\
        Tempo,Par,Lado,Preço,Executado,Quantidade,Taxa
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00054BTC,289.2429BRL,0BTC
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00233BTC,1248.02955BRL,0BTC
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00073BTC,391.01355BRL,0BTC
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00237BTC,1269.45495BRL,0BTC
    """)
    f = tmp_path / "binance_split_fills.csv"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def binance_csv_exact_dup(tmp_path: Path) -> Path:
    """Portuguese format with exact duplicate row."""
    content = textwrap.dedent("""\
        Tempo,Par,Lado,Preço,Executado,Quantidade,Taxa
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00233BTC,1248.02955BRL,0BTC
        26-02-24 20:02:11,BTCBRL,BUY,535635,0.00233BTC,1248.02955BRL,0BTC
        26-02-24 20:02:12,ETHBRL,BUY,17660,0.1054ETH,1861.364BRL,0.0001054ETH
    """)
    f = tmp_path / "binance_exact_dup.csv"
    f.write_text(content, encoding="utf-8")
    return f


def test_can_handle_english_header(extractor: BinanceCsvExtractor, binance_csv_file_english: Path) -> None:
    assert extractor.can_handle(binance_csv_file_english) is True


def test_can_handle_portuguese_header(
    extractor: BinanceCsvExtractor, binance_csv_file_portuguese: Path
) -> None:
    assert extractor.can_handle(binance_csv_file_portuguese) is True


def test_cannot_handle_generic_csv(extractor: BinanceCsvExtractor, tmp_path: Path) -> None:
    generic = tmp_path / "data.csv"
    generic.write_text("date,value\n2024-01-01,100\n", encoding="utf-8")
    assert extractor.can_handle(generic) is False


def test_extract_english_format(
    extractor: BinanceCsvExtractor, binance_csv_file_english: Path
) -> None:
    result = extractor.extract(binance_csv_file_english)
    assert len(result.records) == 3
    assert not result.has_errors


def test_extract_portuguese_format(
    extractor: BinanceCsvExtractor, binance_csv_file_portuguese: Path
) -> None:
    result = extractor.extract(binance_csv_file_portuguese)
    # 3 rows: 1 USDTBRL + 2 BTCBRL (same time, same price) = 2 records after aggregation
    assert len(result.records) == 2
    assert not result.has_errors


def test_extract_asset_code(
    extractor: BinanceCsvExtractor, binance_csv_file_english: Path
) -> None:
    result = extractor.extract(binance_csv_file_english)
    assert len(result.records) >= 1
    assert result.records[0]["asset_code"] == "BTC"
    if len(result.records) >= 2:
        assert result.records[1]["asset_code"] == "ETH"
    if len(result.records) >= 3:
        assert result.records[2]["asset_code"] == "BNB"


def test_extract_operation_types(
    extractor: BinanceCsvExtractor, binance_csv_file_english: Path
) -> None:
    result = extractor.extract(binance_csv_file_english)
    assert len(result.records) >= 1
    assert result.records[0]["operation_type"] == "buy"
    if len(result.records) >= 2:
        assert result.records[1]["operation_type"] == "sell"


def test_extract_operation_date_format_english(
    extractor: BinanceCsvExtractor, binance_csv_file_english: Path
) -> None:
    result = extractor.extract(binance_csv_file_english)
    assert len(result.records) >= 1
    assert result.records[0]["operation_date"] == "2023-06-01"


def test_extract_operation_date_format_portuguese(
    extractor: BinanceCsvExtractor, binance_csv_file_portuguese: Path
) -> None:
    result = extractor.extract(binance_csv_file_portuguese)
    # yy-mm-dd 26-04-13 → 2026-04-13
    assert result.records[0]["operation_date"] == "2026-04-13"


def test_extract_asset_type_is_crypto(
    extractor: BinanceCsvExtractor, binance_csv_file_english: Path
) -> None:
    result = extractor.extract(binance_csv_file_english)
    for record in result.records:
        assert record["asset_type"] == "crypto"


def test_split_fills_aggregation(
    extractor: BinanceCsvExtractor, binance_csv_split_fills: Path
) -> None:
    """Split fills (same timestamp + pair + side + price) should be aggregated."""
    result = extractor.extract(binance_csv_split_fills)
    # 4 split fills → 1 aggregated base only (no quote legs)
    assert len(result.records) == 1
    agg = result.records[0]
    assert agg["asset_code"] == "BTC"
    assert agg["operation_type"] == "buy"
    # Aggregate quantities: 0.00054 + 0.00233 + 0.00073 + 0.00237 = 0.00597
    assert float(agg["quantity"]) == pytest.approx(0.00597, rel=1e-5)
    # Aggregate gross values: 289.2429 + 1248.02955 + 391.01355 + 1269.45495 = 3197.7409
    assert float(agg["gross_value"]) == pytest.approx(3197.7409, rel=1e-4)


def test_exact_duplicate_removal(
    extractor: BinanceCsvExtractor, binance_csv_exact_dup: Path
) -> None:
    """Exact duplicates (all columns identical) should be removed."""
    result = extractor.extract(binance_csv_exact_dup)
    # 3 lines in file, but 1 is exact dup of previous line
    # So after dedup: 2 unique records only (no quote legs)
    assert len(result.records) == 2
    assert not result.has_errors
    # First record should be BTC at 20:02:11
    assert result.records[0]["asset_code"] == "BTC"
    # Second record should be ETH at 20:02:12
    assert result.records[1]["asset_code"] == "ETH"


@pytest.mark.parametrize(
    "pair,expected",
    [
        ("BTCUSDT", "BTC"),
        ("ETHBRL", "ETH"),
        ("BNBBUSD", "BNB"),
        ("SOLUSDT", "SOL"),
        ("DOTBTC", "DOT"),
        ("USDTBRL", "USDT"),
        ("UNKNOWN", "UNKNOWN"),
    ],
)
def test_parse_base_asset(pair: str, expected: str) -> None:
    assert _parse_base_asset(pair) == expected


@pytest.mark.parametrize(
    "date_str,expected",
    [
        ("26-04-13 21:13:14", "2026-04-13"),
        ("25-11-14 20:06:09", "2025-11-14"),
        ("22-02-18 11:36:04", "2022-02-18"),
        ("20-07-26 15:46:28", "2020-07-26"),
    ],
)
def test_normalize_date_yy_mm_dd(date_str: str, expected: str) -> None:
    assert _normalize_date(date_str) == expected

