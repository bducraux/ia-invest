"""Tests for MemberRepository (CRUD, uniqueness, lookups, count_portfolios)."""

from __future__ import annotations

import sqlite3

import pytest

from domain.members import Member
from domain.models import Portfolio
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


@pytest.fixture
def db(tmp_db: Database) -> Database:
    return tmp_db


@pytest.fixture
def repo(db: Database) -> MemberRepository:
    return MemberRepository(db.connection)


def test_upsert_and_get(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob", email="bob@example.com"))
    got = repo.get("bob")
    assert got is not None
    assert got.id == "bob"
    assert got.name == "Bob"
    assert got.email == "bob@example.com"
    assert got.status == "active"
    assert got.created_at is not None and got.updated_at is not None


def test_upsert_updates_existing(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Old", email="old@example.com"))
    repo.upsert(Member(id="bob", name="New", email="new@example.com"))
    got = repo.get("bob")
    assert got is not None
    assert got.name == "New"
    assert got.email == "new@example.com"


def test_email_uniqueness_enforced_at_db_level(
    db: Database, repo: MemberRepository
) -> None:
    repo.upsert(Member(id="a", name="A", email="x@example.com"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert(Member(id="b", name="B", email="x@example.com"))


def test_get_by_email(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob", email="b@x.com"))
    got = repo.get_by_email("b@x.com")
    assert got is not None and got.id == "bob"
    assert repo.get_by_email("missing@x.com") is None


def test_get_by_id_or_name_resolves_id(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob Silva"))
    assert repo.get_by_id_or_name("bob") is not None
    assert repo.get_by_id_or_name("bob silva") is not None
    assert repo.get_by_id_or_name("BOB SILVA") is not None
    assert repo.get_by_id_or_name("missing") is None


def test_list_active_filters_inactive(repo: MemberRepository) -> None:
    repo.upsert(Member(id="a", name="A", status="active"))
    repo.upsert(Member(id="b", name="B", status="inactive"))
    active = repo.list_active()
    assert [m.id for m in active] == ["a", "default"] or [m.id for m in active] == [
        "a",
    ] or "a" in [m.id for m in active]
    # 'default' is auto-seeded by the conftest fixture so it may also appear.
    assert "b" not in [m.id for m in active]


def test_set_status(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob"))
    repo.set_status("bob", "inactive")
    got = repo.get("bob")
    assert got is not None and got.status == "inactive"


def test_count_portfolios(db: Database, repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob"))
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(
        Portfolio(id="rv", name="RV", owner_id="bob", status="active")
    )
    p_repo.upsert(
        Portfolio(id="rf", name="RF", owner_id="bob", status="inactive")
    )
    assert repo.count_portfolios("bob") == 2
    assert repo.count_portfolios("bob", only_active=True) == 1
    assert repo.count_portfolios("missing") == 0


def test_delete_blocked_when_owns_portfolio(
    db: Database, repo: MemberRepository
) -> None:
    repo.upsert(Member(id="bob", name="Bob"))
    PortfolioRepository(db.connection).upsert(
        Portfolio(id="rv", name="RV", owner_id="bob")
    )
    with pytest.raises(ValueError, match="still owns"):
        repo.delete("bob")


def test_delete_succeeds_when_no_portfolios(repo: MemberRepository) -> None:
    repo.upsert(Member(id="bob", name="Bob"))
    repo.delete("bob")
    assert repo.get("bob") is None
