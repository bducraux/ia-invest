"""Tests for the fixed-income CSV importer."""

from __future__ import annotations

import pytest

from normalizers.fixed_income_csv import FixedIncomeCSVImporter

_HEADER = (
    "institution,asset_type,product_name,remuneration_type,application_date,"
    "maturity_date,principal_applied_brl,benchmark,benchmark_percent,"
    "fixed_rate_annual_percent,liquidity_label,imported_gross_value_brl,notes\n"
)


@pytest.fixture
def importer() -> FixedIncomeCSVImporter:
    return FixedIncomeCSVImporter()


def test_imports_pre_cdb_row(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco X,CDB,CDB Pre 12%,PRE,2024-01-02,2026-01-02,"
        "10000.00,NONE,,12.0,D+0,,my note\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert not result.has_errors, result.errors
    pos = result.valid[0]
    assert pos.asset_type == "CDB"
    assert pos.remuneration_type == "PRE"
    assert pos.benchmark == "NONE"
    assert pos.fixed_rate_annual_percent == 12.0
    assert pos.principal_applied_brl == 1_000_000   # cents
    assert pos.investor_type == "PF"


def test_imports_cdi_percent_row(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco Y,LCI,LCI 95% CDI,CDI_PERCENT,2024-01-02,2026-01-02,"
        "5000.00,CDI,95.0,,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert not result.has_errors, result.errors
    pos = result.valid[0]
    assert pos.asset_type == "LCI"
    assert pos.remuneration_type == "CDI_PERCENT"
    assert pos.benchmark == "CDI"
    assert pos.benchmark_percent == 95.0
    assert pos.fixed_rate_annual_percent is None


def test_missing_required_column_is_rejected(importer: FixedIncomeCSVImporter) -> None:
    # Drop principal_applied_brl from the header.
    bad_header = (
        "institution,asset_type,product_name,remuneration_type,"
        "application_date,maturity_date\n"
    )
    csv_text = bad_header + "Banco,CDB,CDB,PRE,2024-01-01,2025-01-01\n"
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors
    assert "principal_applied_brl" in result.errors[0].message


def test_pre_without_fixed_rate_is_rejected(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco,CDB,CDB Pre,PRE,2024-01-02,2026-01-02,1000.00,NONE,,,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors
    assert "fixed_rate_annual_percent" in result.errors[0].message


def test_cdi_percent_without_benchmark_percent_is_rejected(
    importer: FixedIncomeCSVImporter,
) -> None:
    csv_text = _HEADER + (
        "Banco,CDB,CDB CDI,CDI_PERCENT,2024-01-02,2026-01-02,1000.00,CDI,,,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors
    assert "benchmark_percent" in result.errors[0].message


def test_invalid_asset_type_is_rejected(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco,DEBENTURE,Deb,PRE,2024-01-02,2026-01-02,1000.00,NONE,,12.0,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors
    assert "asset_type" in result.errors[0].message


def test_invalid_date_is_rejected(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco,CDB,CDB,PRE,not-a-date,2026-01-02,1000.00,NONE,,12.0,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors


def test_brazilian_money_formatting_is_supported(
    importer: FixedIncomeCSVImporter,
) -> None:
    csv_text = _HEADER + (
        'Banco,CDB,CDB,PRE,2024-01-02,2026-01-02,"1.234,56",NONE,,12.0,,,\n'
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert not result.has_errors, result.errors
    assert result.valid[0].principal_applied_brl == 123_456


def test_zero_principal_is_rejected(importer: FixedIncomeCSVImporter) -> None:
    csv_text = _HEADER + (
        "Banco,CDB,CDB,PRE,2024-01-02,2026-01-02,0,NONE,,12.0,,,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert result.has_errors


def test_imported_gross_value_is_preserved_for_conference(
    importer: FixedIncomeCSVImporter,
) -> None:
    csv_text = _HEADER + (
        "Banco,CDB,CDB,PRE,2024-01-02,2026-01-02,1000.00,NONE,,12.0,,1100.50,\n"
    )
    result = importer.parse_text(csv_text, portfolio_id="p1")
    assert not result.has_errors, result.errors
    assert result.valid[0].imported_gross_value_brl == 110_050
