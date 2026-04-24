"""Tests for SQLiteDailyRateProvider — exposes coverage horizon."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from domain.fixed_income_rates import (
    FlatCDIRateProvider,
    InMemoryCDIRateProvider,
    SQLiteDailyRateProvider,
)
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database


def _provider(tmp_path: Path) -> tuple[BenchmarkRatesRepository, SQLiteDailyRateProvider]:
    db = Database(tmp_path / "test.db")
    db.initialize()
    repo = BenchmarkRatesRepository(db.connection)
    return repo, SQLiteDailyRateProvider(repo)


def test_get_daily_rates_returns_stored_window(tmp_path: Path) -> None:
    repo, provider = _provider(tmp_path)
    repo.upsert_many(
        "CDI",
        [
            (date(2024, 1, 2), Decimal("0.0004")),
            (date(2024, 1, 3), Decimal("0.0005")),
        ],
    )
    out = provider.get_daily_rates(date(2024, 1, 1), date(2024, 1, 31))
    assert out == {
        date(2024, 1, 2): Decimal("0.0004"),
        date(2024, 1, 3): Decimal("0.0005"),
    }


def test_get_coverage_end_returns_max_date(tmp_path: Path) -> None:
    repo, provider = _provider(tmp_path)
    repo.upsert_many(
        "CDI",
        [
            (date(2024, 1, 2), Decimal("0.0004")),
            (date(2024, 6, 5), Decimal("0.0004")),
            (date(2025, 3, 1), Decimal("0.0004")),
        ],
    )
    assert provider.get_coverage_end("CDI") == date(2025, 3, 1)


def test_get_coverage_end_is_none_when_empty(tmp_path: Path) -> None:
    _, provider = _provider(tmp_path)
    assert provider.get_coverage_end("CDI") is None


def test_legacy_providers_have_none_coverage_end() -> None:
    """Backward compat: existing providers expose `None` so the valuation
    service falls back to the strict missing-weekday-as-gap behaviour."""
    flat = FlatCDIRateProvider("0.0004")
    mem = InMemoryCDIRateProvider({"2024-01-02": "0.0004"})
    assert flat.get_coverage_end("CDI") is None
    assert mem.get_coverage_end("CDI") is None
