"""Tests for BrokerCsvExtractor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from extractors.broker_csv import BrokerCsvExtractor


@pytest.fixture
def extractor() -> BrokerCsvExtractor:
    return BrokerCsvExtractor()


@pytest.fixture
def broker_csv_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        date,asset,type,quantity,price,value,fees,broker,account,id
        2024-01-15,PETR4,compra,100,35.00,3500.00,1.50,XP,12345,OP001
        2024-01-20,VALE3,venda,50,75.50,3775.00,1.50,XP,12345,OP002
        2024-02-01,HGLG11,dividendo,200,0,150.00,0,XP,12345,OP003
    """)
    f = tmp_path / "trades.csv"
    f.write_text(content, encoding="utf-8")
    return f


def test_can_handle_csv(extractor: BrokerCsvExtractor, tmp_path: Path) -> None:
    csv_file = tmp_path / "trades.csv"
    csv_file.write_text("header\n", encoding="utf-8")
    assert extractor.can_handle(csv_file) is True


def test_cannot_handle_pdf(extractor: BrokerCsvExtractor, tmp_path: Path) -> None:
    pdf_file = tmp_path / "nota.pdf"
    pdf_file.write_text("%PDF", encoding="utf-8")
    assert extractor.can_handle(pdf_file) is False


def test_extract_returns_correct_record_count(
    extractor: BrokerCsvExtractor, broker_csv_file: Path
) -> None:
    result = extractor.extract(broker_csv_file)
    assert len(result.records) == 3
    assert result.errors == []


def test_extract_maps_canonical_fields(
    extractor: BrokerCsvExtractor, broker_csv_file: Path
) -> None:
    result = extractor.extract(broker_csv_file)
    first = result.records[0]
    assert first["asset_code"] == "PETR4"
    assert first["operation_type"] == "compra"
    assert first["operation_date"] == "2024-01-15"
    assert first["quantity"] == "100"
    assert first["unit_price"] == "35.00"
    assert first["external_id"] == "OP001"


def test_extract_empty_csv_returns_error(
    extractor: BrokerCsvExtractor, tmp_path: Path
) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    result = extractor.extract(empty)
    assert result.has_errors


def test_extract_source_type(
    extractor: BrokerCsvExtractor, broker_csv_file: Path
) -> None:
    result = extractor.extract(broker_csv_file)
    assert result.source_type == "broker_csv"
