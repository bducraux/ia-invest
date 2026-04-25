"""Tests for AvenueAliasesRepository (avenue_symbol_aliases table)."""

from __future__ import annotations

from pathlib import Path

from storage.repository.avenue_aliases import AvenueAliasesRepository, normalize_name
from storage.repository.db import Database


def _make_repo(tmp_path: Path) -> tuple[Database, AvenueAliasesRepository]:
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db, AvenueAliasesRepository(db.connection)


def test_normalize_name_collapses_whitespace_and_uppercases() -> None:
    assert normalize_name("  Alphabet   inc  ") == "ALPHABET INC"
    assert normalize_name("alphabet\tinc") == "ALPHABET INC"
    assert normalize_name("") == ""


def test_upsert_and_get(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "Alphabet Inc Class A Common Stock", "GOOGL", cusip="02079K305")

    hit = repo.get("p1", "alphabet inc class a common stock")
    assert hit == ("GOOGL", "02079K305")

    miss = repo.get("p1", "Tesla Inc")
    assert miss is None


def test_upsert_preserves_cusip_when_not_provided(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "Tesla Inc Common Stock", "TSLA", cusip="88160R101")
    repo.upsert("p1", "Tesla Inc Common Stock", "TSLA", cusip=None)
    hit = repo.get("p1", "tesla inc common stock")
    assert hit == ("TSLA", "88160R101")


def test_upsert_updates_asset_code_on_conflict(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "Some Name", "OLD")
    repo.upsert("p1", "Some Name", "NEW", cusip="123456789")
    hit = repo.get("p1", "some name")
    assert hit == ("NEW", "123456789")


def test_aliases_are_per_portfolio(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "Foo", "FOO")
    repo.upsert("p2", "Foo", "BAR")
    assert repo.get("p1", "foo") == ("FOO", None)
    assert repo.get("p2", "foo") == ("BAR", None)


def test_upsert_ignores_blank_inputs(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "", "GOOGL")
    repo.upsert("p1", "Foo", "")
    assert repo.get("p1", "") is None
    assert repo.get("p1", "foo") is None


def test_list_all_returns_normalized_keys(tmp_path: Path) -> None:
    _, repo = _make_repo(tmp_path)
    repo.upsert("p1", "Alphabet Inc", "GOOGL", cusip="02079K305")
    repo.upsert("p1", "Tesla Inc", "TSLA")
    result = repo.list_all("p1")
    assert result == {
        "ALPHABET INC": ("GOOGL", "02079K305"),
        "TESLA INC": ("TSLA", None),
    }
