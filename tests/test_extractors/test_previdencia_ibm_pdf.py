from __future__ import annotations

from pathlib import Path

from extractors.previdencia_ibm_pdf import PrevidenciaIbmPdfExtractor


def _sample_pdf_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "previdencia"
        / "extrato_março_2026.pdf"
    )


def test_can_handle_ibm_previdencia_pdf() -> None:
    extractor = PrevidenciaIbmPdfExtractor()
    assert extractor.can_handle(_sample_pdf_path()) is True


def test_extract_snapshot_fields_from_pdf() -> None:
    extractor = PrevidenciaIbmPdfExtractor()
    result = extractor.extract(_sample_pdf_path())

    assert result.errors == []
    assert result.source_type == "previdencia_ibm_pdf"
    assert len(result.records) == 1

    record = result.records[0]
    assert record["asset_code"] == "PREV_IBM_CD"
    assert record["product_name"] == "IBM CD"
    assert record["period_start_date"] == "2026-03-01"
    assert record["period_end_date"] == "2026-03-31"
    assert record["period_month"] == "2026-03"
    assert abs(float(record["quantity"]) - 9104.7430) < 0.0001
    assert int(record["unit_price_cents"]) == 4751
    assert int(record["market_value_cents"]) > 0
