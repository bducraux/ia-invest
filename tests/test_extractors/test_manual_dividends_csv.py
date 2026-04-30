"""Tests for ManualDividendsCsvExtractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from extractors.manual_dividends_csv import ManualDividendsCsvExtractor


@pytest.fixture
def extractor() -> ManualDividendsCsvExtractor:
    return ManualDividendsCsvExtractor()


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    f = tmp_path / "dividend_history.csv"
    f.write_text(
        "data_pagamento,ticker,tipo,quantidade,valor_total\n"
        "2018-12-17,TRPL4,dividendo,100,384.29\n"
        "2018-12-17,TRPL4,jcp,100,305.49\n"
        "2025-11-27,BTAL11,rendimento,10,9.50\n",
        encoding="utf-8",
    )
    return f


def test_can_handle(extractor: ManualDividendsCsvExtractor, sample_csv: Path) -> None:
    assert extractor.can_handle(sample_csv) is True


def test_cannot_handle_unrelated_csv(extractor: ManualDividendsCsvExtractor, tmp_path: Path) -> None:
    f = tmp_path / "other.csv"
    f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert extractor.can_handle(f) is False


def test_cannot_handle_xlsx(extractor: ManualDividendsCsvExtractor, tmp_path: Path) -> None:
    f = tmp_path / "x.xlsx"
    f.write_bytes(b"")
    assert extractor.can_handle(f) is False


def test_dividendo_record(extractor: ManualDividendsCsvExtractor, sample_csv: Path) -> None:
    rec = next(r for r in extractor.extract(sample_csv).records if r["operation_type"] == "dividend")
    assert rec["asset_code"] == "TRPL4"
    assert rec["operation_date"] == "2018-12-17"
    assert rec["quantity"] == 100
    assert rec["gross_value"] == pytest.approx(384.29)
    assert rec["fees"] == 0
    assert rec["source"] == "manual_dividends_csv"


def test_jcp_estimates_15pct_ir(extractor: ManualDividendsCsvExtractor, sample_csv: Path) -> None:
    rec = next(r for r in extractor.extract(sample_csv).records if r["operation_type"] == "jcp")
    assert rec["asset_code"] == "TRPL4"
    assert rec["gross_value"] == pytest.approx(305.49)
    # 15% of 305.49 = 45.8235 → rounded to cents 45.82 BRL
    assert rec["fees"] == pytest.approx(round(30549 * 0.15) / 100.0)


def test_rendimento_no_ir(extractor: ManualDividendsCsvExtractor, sample_csv: Path) -> None:
    rec = next(r for r in extractor.extract(sample_csv).records if r["operation_type"] == "rendimento")
    assert rec["asset_code"] == "BTAL11"
    assert rec["gross_value"] == pytest.approx(9.50)
    assert rec["fees"] == 0


def test_external_id_is_deterministic(
    extractor: ManualDividendsCsvExtractor, sample_csv: Path
) -> None:
    a = extractor.extract(sample_csv).records
    b = extractor.extract(sample_csv).records
    assert [r["external_id"] for r in a] == [r["external_id"] for r in b]
    div = next(r for r in a if r["operation_type"] == "dividend")
    assert div["external_id"] == "manual_div:2018-12-17:dividend:TRPL4:38429"


def test_invalid_tipo_goes_to_errors(
    extractor: ManualDividendsCsvExtractor, tmp_path: Path
) -> None:
    f = tmp_path / "bad.csv"
    f.write_text(
        "data_pagamento,ticker,tipo,quantidade,valor_total\n"
        "2024-01-01,PETR4,bonificacao,100,50.00\n",
        encoding="utf-8",
    )
    result = extractor.extract(f)
    assert result.records == []
    assert len(result.errors) == 1
    assert "Unknown tipo" in result.errors[0]["message"]


def test_three_records_emitted(
    extractor: ManualDividendsCsvExtractor, sample_csv: Path
) -> None:
    result = extractor.extract(sample_csv)
    assert len(result.records) == 3
    assert result.errors == []
