"""Tests for ManualXlsxB3Extractor."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from extractors.manual_xlsx_b3 import ManualXlsxB3Extractor
from normalizers.operations import OperationNormalizer


def _make_b3_manual_xlsx(tmp_path: Path, rows: list[tuple]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Ativo",
        "Tipo",
        "Data da transação",
        "Quantidade",
        "Preço",
        "Valor total",
        "Custodiante",
        None,
    ])
    for row in rows:
        ws.append(list(row))
    path = tmp_path / "manual_xlsx_b3.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def extractor() -> ManualXlsxB3Extractor:
    return ManualXlsxB3Extractor()


@pytest.fixture
def b3_manual_file(tmp_path: Path) -> Path:
    return _make_b3_manual_xlsx(
        tmp_path,
        [
            ("BBAS3", "Compra", 45994, 5, "R$ 22,54", "R$ 112,70", "INTER DTVM", None),
            ("VISC11", "Venda", 45994, 10, "R$ 108,64", "R$ 1.086,40", "INTER DTVM", None),
            (
                "RBRY11",
                "Transferência de Custódia",
                45849,
                10,
                "R$ 93,22",
                "R$ 932,20",
                "XP INVESTIMENTOS CCTVM",
                None,
            ),
            (
                "TRPL4",
                "Ajustes de Posição Inicial",
                43832,
                400,
                "R$ 22,77",
                "R$ 9.108,00",
                "CLEAR DTVM",
                None,
            ),
        ],
    )


def test_can_handle_manual_b3_xlsx(extractor: ManualXlsxB3Extractor, b3_manual_file: Path) -> None:
    assert extractor.can_handle(b3_manual_file) is True


def test_extract_maps_manual_b3_records(extractor: ManualXlsxB3Extractor, b3_manual_file: Path) -> None:
    result = extractor.extract(b3_manual_file)

    assert result.source_type == "manual_xlsx_b3"
    assert result.errors == []
    assert len(result.records) == 4

    first = result.records[0]
    assert first["asset_code"] == "BBAS3"
    assert first["operation_type"] == "buy"
    assert first["operation_date"] == "2025-12-03"
    assert first["quantity"] == pytest.approx(5.0)
    assert first["unit_price"] == pytest.approx(22.54)
    assert first["gross_value"] == pytest.approx(112.70)
    assert first["asset_type"] is None


def test_extract_maps_transfer_and_initial_adjustment_to_transfer_in(
    extractor: ManualXlsxB3Extractor, b3_manual_file: Path
) -> None:
    records = extractor.extract(b3_manual_file).records
    ops_by_asset = {record["asset_code"]: record["operation_type"] for record in records}

    assert ops_by_asset["RBRY11"] == "transfer_in"
    assert ops_by_asset["TRPL4"] == "transfer_in"


def test_normalizer_infers_b3_asset_types_from_generic_manual_records(
    extractor: ManualXlsxB3Extractor, b3_manual_file: Path
) -> None:
    records = extractor.extract(b3_manual_file).records
    normalizer = OperationNormalizer()

    result = normalizer.normalize(records, portfolio_id="renda-variavel-bruno")

    assert result.errors == []
    asset_types = {op.asset_code: op.asset_type for op in result.valid}
    assert asset_types["BBAS3"] == "stock"
    assert asset_types["VISC11"] == "fii"
    assert asset_types["RBRY11"] == "fii"


class TestRealFile:
    """Smoke tests against the B3 manual-bootstrap XLSX fixture."""

    FIXTURE_FILE = Path("tests/fixtures/b3_transactions.xlsx")

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        if not self.FIXTURE_FILE.exists():
            pytest.skip(f"B3 manual XLSX test fixture not found: {self.FIXTURE_FILE}")

    def test_extracts_multiple_operation_types(self, extractor: ManualXlsxB3Extractor) -> None:
        result = extractor.extract(self.FIXTURE_FILE)
        assert result.errors == []
        assert len(result.records) == 17

        operation_types = {r["operation_type"] for r in result.records}
        assert "buy" in operation_types
        assert "sell" in operation_types
        assert "transfer_in" in operation_types

    def test_normalizer_infers_stock_and_fii_types(self, extractor: ManualXlsxB3Extractor) -> None:
        result = extractor.extract(self.FIXTURE_FILE)
        records = result.records

        normalizer = OperationNormalizer()
        norm_result = normalizer.normalize(records, portfolio_id="renda-variavel-bruno")

        asset_types = {op.asset_code: op.asset_type for op in norm_result.valid}

        # Verify known assets from fixture
        assert asset_types["BBAS3"] == "stock"
        assert asset_types["VISC11"] == "fii"
        assert asset_types["RBRY11"] == "fii"
        assert asset_types["WEGE3"] == "stock"
