"""Tests for the BenchmarkRatesRepository (daily_benchmark_rates cache)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database


def _make_repo(tmp_path: Path) -> tuple[Database, BenchmarkRatesRepository]:
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db, BenchmarkRatesRepository(db.connection)


def test_upsert_many_and_get_range_roundtrip(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    rows = [
        (date(2024, 1, 2), Decimal("0.00043739")),
        (date(2024, 1, 3), Decimal("0.00043739")),
        (date(2024, 1, 4), Decimal("0.00043800")),
    ]
    inserted = repo.upsert_many("CDI", rows)
    assert inserted == 3

    out = repo.get_range("CDI", date(2024, 1, 2), date(2024, 1, 4))
    assert out == {
        date(2024, 1, 2): Decimal("0.00043739"),
        date(2024, 1, 3): Decimal("0.00043739"),
        date(2024, 1, 4): Decimal("0.00043800"),
    }


def test_get_range_filters_to_window(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "CDI",
        [
            (date(2024, 1, 2), Decimal("0.0004")),
            (date(2024, 1, 3), Decimal("0.0004")),
            (date(2024, 1, 4), Decimal("0.0004")),
        ],
    )
    out = repo.get_range("CDI", date(2024, 1, 3), date(2024, 1, 3))
    assert list(out.keys()) == [date(2024, 1, 3)]


def test_upsert_replaces_existing_value(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [(date(2024, 1, 2), Decimal("0.0001"))])
    repo.upsert_many("CDI", [(date(2024, 1, 2), Decimal("0.0009"))])
    out = repo.get_range("CDI", date(2024, 1, 2), date(2024, 1, 2))
    assert out[date(2024, 1, 2)] == Decimal("0.0009")


def test_get_coverage_empty_returns_none(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    assert repo.get_coverage("CDI") == (None, None, 0)


def test_get_coverage_returns_min_max_count(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "CDI",
        [
            (date(2024, 1, 2), Decimal("0.0004")),
            (date(2024, 6, 5), Decimal("0.0004")),
            (date(2025, 3, 1), Decimal("0.0004")),
        ],
    )
    start, end, count = repo.get_coverage("CDI")
    assert start == date(2024, 1, 2)
    assert end == date(2025, 3, 1)
    assert count == 3


def test_benchmarks_are_isolated_by_name(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [(date(2024, 1, 2), Decimal("0.0004"))])
    repo.upsert_many("SELIC", [(date(2024, 1, 3), Decimal("0.0005"))])
    assert repo.get_coverage("CDI") == (date(2024, 1, 2), date(2024, 1, 2), 1)
    assert repo.get_coverage("SELIC") == (date(2024, 1, 3), date(2024, 1, 3), 1)
    cdi_range = repo.get_range("CDI", date(2024, 1, 1), date(2024, 1, 31))
    assert list(cdi_range.keys()) == [date(2024, 1, 2)]


def test_benchmark_name_is_normalised_to_uppercase(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many("cdi", [(date(2024, 1, 2), Decimal("0.0004"))])
    assert repo.get_coverage("CDI")[2] == 1
    assert repo.get_range("cdi", date(2024, 1, 2), date(2024, 1, 2))


def test_decimal_precision_is_preserved(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    high_precision = Decimal("0.000437391234567890")
    repo.upsert_many("CDI", [(date(2024, 1, 2), high_precision)])
    out = repo.get_range("CDI", date(2024, 1, 2), date(2024, 1, 2))
    assert out[date(2024, 1, 2)] == high_precision


def test_iso_date_strings_are_accepted(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [("2024-01-02", "0.0004")])
    out = repo.get_range("CDI", "2024-01-01", "2024-01-31")
    assert out == {date(2024, 1, 2): Decimal("0.0004")}
