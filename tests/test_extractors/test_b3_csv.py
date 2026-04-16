"""Tests for B3CsvExtractor."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from extractors.b3_csv import B3CsvExtractor


@pytest.fixture
def extractor() -> B3CsvExtractor:
    return B3CsvExtractor()


@pytest.fixture
def b3_xlsx_file(tmp_path: Path) -> Path:
    rows = [
        {
            "Data do Negócio": "03/12/2025",
            "Tipo de Movimentação": "Compra",
            "Mercado": "Mercado Fracionário",
            "Prazo/Vencimento": "-",
            "Instituição": "INTER",
            "Código de Negociação": "BBAS3F",
            "Quantidade": 5,
            "Preço": 22.54,
            "Valor": 112.70,
        },
        {
            "Data do Negócio": "03/12/2025",
            "Tipo de Movimentação": "Venda",
            "Mercado": "Mercado à Vista",
            "Prazo/Vencimento": "-",
            "Instituição": "INTER",
            "Código de Negociação": "VISC11",
            "Quantidade": 10,
            "Preço": 108.64,
            "Valor": 1086.40,
        },
    ]
    f = tmp_path / "b3_negociacao.xlsx"
    pd.DataFrame(rows).to_excel(f, index=False)
    return f


def test_can_handle_b3_xlsx(extractor: B3CsvExtractor, b3_xlsx_file: Path) -> None:
    assert extractor.can_handle(b3_xlsx_file) is True


def test_cannot_handle_unrelated_csv(extractor: B3CsvExtractor, tmp_path: Path) -> None:
    f = tmp_path / "generic.csv"
    f.write_text("date,asset,price\n2025-01-01,PETR4,30\n", encoding="utf-8")
    assert extractor.can_handle(f) is False


def test_extract_maps_records(extractor: B3CsvExtractor, b3_xlsx_file: Path) -> None:
    result = extractor.extract(b3_xlsx_file)
    assert len(result.records) == 2
    assert result.errors == []

    first = result.records[0]
    assert first["source"] == "b3_csv"
    assert first["asset_code"] == "BBAS3"
    assert first["operation_type"] == "compra"
    assert first["operation_date"] == "03/12/2025"
    assert first["quantity"] == 5
    assert first["unit_price"] == 22.54
    assert first["gross_value"] == 112.7


def test_extract_source_type(extractor: B3CsvExtractor, b3_xlsx_file: Path) -> None:
    result = extractor.extract(b3_xlsx_file)
    assert result.source_type == "b3_csv"
