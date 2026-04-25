"""Tests for AvenueApexPdfExtractor (Avenue/Apex monthly statements)."""

from __future__ import annotations

from pathlib import Path

import pytest

from extractors.avenue_apex_pdf import AvenueApexPdfExtractor
from storage.repository.avenue_aliases import AvenueAliasesRepository
from storage.repository.db import Database

_PROCESSED = (
    Path(__file__).resolve().parents[2]
    / "portfolios"
    / "internacional-bruno"
    / "processed"
)


def _pdf(name: str) -> Path:
    return _PROCESSED / name


def _make_repo(tmp_path: Path) -> AvenueAliasesRepository:
    db = Database(tmp_path / "t.db")
    db.initialize()
    return AvenueAliasesRepository(db.connection)


@pytest.fixture(scope="module", autouse=True)
def _require_fixtures() -> None:
    """Skip the module if the real PDFs are absent (e.g. CI without portfolios)."""
    needed = [
        "relatorio-apex-julho-2022.pdf",
        "relatorio-apex-novembro-2023.pdf",
        "relatorio-apex-marco-2026.pdf",
    ]
    missing = [name for name in needed if not _pdf(name).is_file()]
    if missing:
        pytest.skip(f"Missing Avenue/Apex sample PDFs: {missing}")


def test_can_handle_apex_pdf() -> None:
    ext = AvenueApexPdfExtractor()
    assert ext.can_handle(_pdf("relatorio-apex-novembro-2023.pdf")) is True


def test_can_handle_rejects_non_pdf(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert AvenueApexPdfExtractor().can_handle(f) is False


def test_extracts_buy_records_with_summary_resolution() -> None:
    ext = AvenueApexPdfExtractor()
    result = ext.extract(_pdf("relatorio-apex-novembro-2023.pdf"))

    assert result.errors == []
    buys = [r for r in result.records if r.get("operation_type") == "buy"]
    by_code = {r["asset_code"]: r for r in buys}

    googl = by_code["GOOGL"]
    assert googl["operation_date"] == "2023-11-15"
    assert googl["settlement_date"] == "2023-11-15"
    assert googl["trade_currency"] == "USD"
    assert googl["asset_type"] == "stock_us"
    assert googl["quantity"] == pytest.approx(2.00078)
    assert googl["unit_price"] == pytest.approx(132.448)
    assert googl["gross_value"] == pytest.approx(265.0)
    assert googl["broker"] == "Avenue"
    assert googl["source"] == "avenue_apex_pdf"

    assert by_code["KO"]["quantity"] == pytest.approx(4.08599)
    assert by_code["TSLA"]["quantity"] == pytest.approx(1.00174)


def test_extracts_stock_split_as_split_bonus() -> None:
    ext = AvenueApexPdfExtractor()
    result = ext.extract(_pdf("relatorio-apex-julho-2022.pdf"))

    assert result.errors == []
    splits = [r for r in result.records if r.get("operation_type") == "split_bonus"]
    assert len(splits) == 1
    googl_split = splits[0]
    assert googl_split["asset_code"] == "GOOGL"
    assert googl_split["operation_date"] == "2022-07-20"
    assert googl_split["quantity"] == pytest.approx(0.40356)
    assert googl_split["unit_price"] == 0
    assert googl_split["gross_value"] == 0
    assert googl_split["trade_currency"] == "BRL"


def test_unresolved_name_without_summary_or_cache_yields_error(tmp_path: Path) -> None:
    """April 2021 has no PORTFOLIO SUMMARY (cash-only month-end) and the BUY
    block names like 'AMAZON.COM INC' must therefore come from the persistent
    cache. Without one, every BOUGHT row should produce a structured error.
    """
    pdf = _pdf("relatorio-apex-abril-2021.pdf")
    if not pdf.is_file():
        pytest.skip("April 2021 sample missing")
    ext = AvenueApexPdfExtractor()  # no alias_repo
    result = ext.extract(pdf)
    assert result.records == []
    assert result.errors, "expected unresolved-name errors"
    for err in result.errors:
        assert err["error_type"] == "validation"
        assert "Could not resolve" in err["message"]


def test_persistent_cache_resolves_legacy_month(tmp_path: Path) -> None:
    """Pre-pass harvest from a later month must let April 2021 resolve."""
    pdf_apr = _pdf("relatorio-apex-abril-2021.pdf")
    pdf_jul = _pdf("relatorio-apex-julho-2022.pdf")
    if not pdf_apr.is_file() or not pdf_jul.is_file():
        pytest.skip("Required samples missing")

    repo = _make_repo(tmp_path)

    # Harvest from July 2022 (has full PORTFOLIO SUMMARY).
    harvester = AvenueApexPdfExtractor(alias_repo=repo, portfolio_id="p1")
    harvester.harvest_aliases(pdf_jul)

    # Now extract April 2021 — descriptions must resolve via the cache.
    importer = AvenueApexPdfExtractor(alias_repo=repo, portfolio_id="p1")
    result = importer.extract(pdf_apr)

    buys = [r for r in result.records if r.get("operation_type") == "buy"]
    codes = {r["asset_code"] for r in buys}
    assert {"AMZN", "GOOGL", "KO", "JNJ", "TSLA"}.issubset(codes)
    assert all(r["trade_currency"] == "USD" for r in buys)


def test_summary_only_records_no_dividends_no_journals() -> None:
    """V1 ignores dividends, fees, journals — they must NOT appear as records."""
    ext = AvenueApexPdfExtractor()
    result = ext.extract(_pdf("relatorio-apex-marco-2026.pdf"))
    # March 2026 has only dividends + journals (no buys).
    assert result.records == []
    assert result.errors == []
