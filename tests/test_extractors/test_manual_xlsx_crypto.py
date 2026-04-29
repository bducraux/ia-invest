"""Tests for ManualXlsxCryptoExtractor."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from extractors.manual_xlsx_crypto import (
    ManualXlsxCryptoExtractor,
    _excel_serial_to_date,
    _parse_brl,
)

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestExcelSerialToDate:
    def test_known_date_2026(self):
        # Excel 46059 → 2026-02-06 (verified manually)
        assert _excel_serial_to_date(46059) == "2026-02-06"

    def test_known_date_2020(self):
        # Excel 43923 → 2020-04-02
        assert _excel_serial_to_date(43923) == "2020-04-02"

    def test_known_old_date_2018(self):
        # Excel 43145 → 2018-02-14
        assert _excel_serial_to_date(43145) == "2018-02-14"

    def test_none_returns_none(self):
        assert _excel_serial_to_date(None) is None

    def test_invalid_returns_none(self):
        assert _excel_serial_to_date("not-a-date") is None


class TestParseBrl:
    def test_full_format(self):
        assert _parse_brl("R$ 371.032,00") == 371032.0

    def test_small_value(self):
        assert _parse_brl("R$ 1.146,49") == 1146.49

    def test_zero(self):
        assert _parse_brl("R$ 0,00") == 0.0

    def test_single_unit(self):
        assert _parse_brl("R$ 1,00") == 1.0

    def test_no_prefix(self):
        assert _parse_brl("5,45") == 5.45

    def test_none(self):
        assert _parse_brl(None) == 0.0


# ---------------------------------------------------------------------------
# XLSX fixture builder
# ---------------------------------------------------------------------------


def _make_xlsx(tmp_path: Path, rows: list[tuple]) -> Path:
    """Create a minimal manual-bootstrap XLSX with given data rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Data de modificação",
        "Ativo",
        "Tipo",
        "Data da transação",
        "Quantidade",
        "Preço",
        "Valor total",
        "Custodiante",
        None,
        None,
    ])
    for row in rows:
        ws.append(list(row))
    path = tmp_path / "manual_xlsx_test.xlsx"
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Extractor integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def extractor() -> ManualXlsxCryptoExtractor:
    return ManualXlsxCryptoExtractor()


@pytest.fixture
def simple_buy_file(tmp_path: Path) -> Path:
    """Single BTC buy row."""
    return _make_xlsx(tmp_path, [
        (46059, "BTC", "Compra", 46059, 0.00309, "R$ 371.032,00", "R$ 1.146,49", "BINANCE BRASIL", None, None),
    ])


@pytest.fixture
def simple_sell_file(tmp_path: Path) -> Path:
    """Single USDT sell row."""
    return _make_xlsx(tmp_path, [
        (45947, "USDT", "Venda", 45947, 332.8090718, "R$ 5,45", "R$ 1.813,45", "BINANCE BRASIL", None, None),
    ])


@pytest.fixture
def zero_price_file(tmp_path: Path) -> Path:
    """Row with zero price (e.g. coin-to-coin rewards)."""
    return _make_xlsx(tmp_path, [
        (45821, "ADA", "Compra", 44888, 15.997759, "R$ 0,00", "R$ 0,00", "BINANCE BRASIL", None, None),
    ])


@pytest.fixture
def multi_row_file(tmp_path: Path) -> Path:
    """Multiple rows with different assets and brokers."""
    return _make_xlsx(tmp_path, [
        (46059, "BTC", "Compra", 46059, 0.00309, "R$ 371.032,00", "R$ 1.146,49", "BINANCE BRASIL", None, None),
        (45947, "USDT", "Venda", 45947, 332.809, "R$ 5,45", "R$ 1.813,45", "BINANCE BRASIL", None, None),
        (45821, "ETH", "Compra", 43923, 6.51, "R$ 715,00", "R$ 4.654,65", "COINBASE", None, None),
        (45821, "ONDO", "Compra", 45413, 3282.0473, "R$ 4,00", "R$ 13.128,19", "KUCOIN", None, None),
    ])


class TestCanHandle:
    def test_accepts_manual_xlsx(self, extractor, simple_buy_file):
        assert extractor.can_handle(simple_buy_file) is True

    def test_rejects_csv(self, extractor, tmp_path):
        f = tmp_path / "trades.csv"
        f.write_text("date,asset\n2023-01-01,BTC\n")
        assert extractor.can_handle(f) is False

    def test_rejects_unrelated_xlsx(self, extractor, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Date", "Price", "Volume"])
        ws.append([1, 2, 3])
        path = tmp_path / "other.xlsx"
        wb.save(path)
        assert extractor.can_handle(path) is False


class TestExtractBuy:
    def test_returns_one_record(self, extractor, simple_buy_file):
        result = extractor.extract(simple_buy_file)
        assert len(result.records) == 1
        assert result.errors == []

    def test_operation_type_buy(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["operation_type"] == "buy"

    def test_asset_code(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["asset_code"] == "BTC"

    def test_operation_date(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["operation_date"] == "2026-02-06"

    def test_quantity(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["quantity"] == pytest.approx(0.00309)

    def test_unit_price_parsed_brl(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["unit_price"] == pytest.approx(371032.0)

    def test_gross_value_parsed_brl(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["gross_value"] == pytest.approx(1146.49)

    def test_broker_preserved(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["broker"] == "BINANCE BRASIL"

    def test_quote_currency_is_brl(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["quote_currency"] == "BRL"

    def test_source_type(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["source"] == "manual_xlsx_crypto"

    def test_asset_type_is_crypto(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert rec["asset_type"] == "crypto"

    def test_external_id_includes_date_and_asset(self, extractor, simple_buy_file):
        rec = extractor.extract(simple_buy_file).records[0]
        assert "manual_xlsx:" in rec["external_id"]
        assert "2026-02-06" in rec["external_id"]
        assert "BTC" in rec["external_id"]


class TestExtractSell:
    def test_operation_type_sell(self, extractor, simple_sell_file):
        rec = extractor.extract(simple_sell_file).records[0]
        assert rec["operation_type"] == "sell"

    def test_sell_quantity(self, extractor, simple_sell_file):
        rec = extractor.extract(simple_sell_file).records[0]
        assert rec["quantity"] == pytest.approx(332.8090718)


class TestZeroPrice:
    def test_zero_price_imported_without_error(self, extractor, zero_price_file):
        result = extractor.extract(zero_price_file)
        assert result.errors == []
        assert len(result.records) == 1

    def test_zero_price_value(self, extractor, zero_price_file):
        rec = extractor.extract(zero_price_file).records[0]
        assert rec["unit_price"] == 0.0
        assert rec["gross_value"] == 0.0


class TestMultiRow:
    def test_all_records_extracted(self, extractor, multi_row_file):
        result = extractor.extract(multi_row_file)
        assert result.errors == []
        assert len(result.records) == 4

    def test_asset_types(self, extractor, multi_row_file):
        records = extractor.extract(multi_row_file).records
        assets = [r["asset_code"] for r in records]
        assert "BTC" in assets
        assert "USDT" in assets
        assert "ETH" in assets
        assert "ONDO" in assets

    def test_brokers(self, extractor, multi_row_file):
        records = extractor.extract(multi_row_file).records
        brokers = {r["broker"] for r in records}
        assert brokers == {"BINANCE BRASIL", "COINBASE", "KUCOIN"}

    def test_mixed_operations(self, extractor, multi_row_file):
        records = extractor.extract(multi_row_file).records
        types = {r["operation_type"] for r in records}
        assert types == {"buy", "sell"}


class TestExternalIdUniqueness:
    def test_two_different_records_have_different_ids(self, extractor, multi_row_file):
        records = extractor.extract(multi_row_file).records
        ids = [r["external_id"] for r in records]
        assert len(ids) == len(set(ids)), "external_ids must be unique across records"


class TestRealFile:
    """Smoke tests against the manual-bootstrap XLSX fixture."""

    FIXTURE_FILE = Path("tests/fixtures/manual_xlsx_transactions.xlsx")

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        if not self.FIXTURE_FILE.exists():
            pytest.skip(f"Manual XLSX test fixture not found: {self.FIXTURE_FILE}")

    def test_extracts_94_records(self, extractor):
        result = extractor.extract(self.FIXTURE_FILE)
        assert result.errors == []
        assert len(result.records) == 94

    def test_one_sell_record(self, extractor):
        records = extractor.extract(self.FIXTURE_FILE).records
        sells = [r for r in records if r["operation_type"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["asset_code"] == "USDT"

    def test_btc_total_quantity(self, extractor):
        """BTC net quantity from manual XLSX data matches expected accumulation."""
        records = extractor.extract(self.FIXTURE_FILE).records
        btc = [r for r in records if r["asset_code"] == "BTC"]
        total = sum(r["quantity"] for r in btc)
        # Should be positive; rough sanity check (> 0.4 BTC total purchased)
        assert total > 0.4

    def test_all_records_have_brl_quote(self, extractor):
        records = extractor.extract(self.FIXTURE_FILE).records
        for rec in records:
            assert rec["quote_currency"] == "BRL", f"Record {rec['external_id']} has wrong quote currency"

    def test_no_rndr_asset_code(self, extractor):
        """RNDR should be mapped to RENDER."""
        records = extractor.extract(self.FIXTURE_FILE).records
        asset_codes = {r["asset_code"] for r in records}
        assert "RNDR" not in asset_codes, "RNDR should be aliased to RENDER"
