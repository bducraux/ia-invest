"""Tests for the FxRatesRepository (fx_rates cache)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from storage.repository.db import Database
from storage.repository.fx_rates import FxRatesRepository


def _make_repo(tmp_path: Path) -> tuple[Database, FxRatesRepository]:
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db, FxRatesRepository(db.connection)


def test_upsert_and_get_rate_exact(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "USDBRL",
        [
            (date(2024, 5, 17), Decimal("5.1234")),
            (date(2024, 5, 20), Decimal("5.2000")),
        ],
        source="bacen_ptax",
    )
    rate = repo.get_rate("USDBRL", date(2024, 5, 20))
    assert rate is not None
    value, source = rate
    assert value == Decimal("5.2000")
    assert source == "bacen_ptax"


def test_get_latest_on_or_before_handles_weekend(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "USDBRL",
        [(date(2024, 5, 17), Decimal("5.1234"))],
        source="bacen_ptax",
    )
    out = repo.get_latest_on_or_before("USDBRL", date(2024, 5, 19))
    assert out is not None
    found_date, value, source = out
    assert found_date == date(2024, 5, 17)
    assert value == Decimal("5.1234")
    assert source == "bacen_ptax"


def test_upsert_overwrites_existing(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "USDBRL",
        [(date(2024, 5, 17), Decimal("5.0"))],
        source="initial",
    )
    repo.upsert_many(
        "USDBRL",
        [(date(2024, 5, 17), Decimal("5.5"))],
        source="updated",
    )
    rate = repo.get_rate("USDBRL", date(2024, 5, 17))
    assert rate == (Decimal("5.5"), "updated")


def test_coverage_reports_min_max_count(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert_many(
        "USDBRL",
        [
            (date(2024, 1, 5), Decimal("4.9")),
            (date(2024, 6, 1), Decimal("5.1")),
        ],
        source="bacen_ptax",
    )
    min_d, max_d, n = repo.get_coverage("USDBRL")
    assert min_d == date(2024, 1, 5)
    assert max_d == date(2024, 6, 1)
    assert n == 2
