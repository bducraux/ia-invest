"""Tests for MemberService business rules."""

from __future__ import annotations

import pytest

from domain.members import Member, MemberService, MemberServiceError
from domain.models import Portfolio
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


@pytest.fixture
def db(tmp_db: Database) -> Database:
    return tmp_db


@pytest.fixture
def svc(db: Database) -> MemberService:
    return MemberService(
        MemberRepository(db.connection),
        PortfolioRepository(db.connection),
    )


def test_create_member_minimal(svc: MemberService) -> None:
    member = svc.create(member_id="bob", name="Bob")
    assert member.id == "bob"
    assert member.name == "Bob"
    assert member.status == "active"


def test_create_member_with_email(svc: MemberService) -> None:
    member = svc.create(
        member_id="bob",
        name="Bob",
        email="bob@example.com",
        display_name="Bob S.",
    )
    assert member.email == "bob@example.com"
    assert member.display_name == "Bob S."


def test_create_invalid_email_rejected(svc: MemberService) -> None:
    with pytest.raises(MemberServiceError, match="Invalid email"):
        svc.create(member_id="bob", name="Bob", email="not-an-email")


def test_create_duplicate_email_rejected(svc: MemberService) -> None:
    svc.create(member_id="a", name="A", email="x@x.com")
    with pytest.raises(MemberServiceError, match="already used"):
        svc.create(member_id="b", name="B", email="x@x.com")


def test_create_invalid_id_rejected(svc: MemberService) -> None:
    with pytest.raises(MemberServiceError, match="Invalid member id"):
        svc.create(member_id="Bob!", name="Bob")


def test_create_duplicate_id_rejected(svc: MemberService) -> None:
    svc.create(member_id="bob", name="Bob")
    with pytest.raises(MemberServiceError, match="already exists"):
        svc.create(member_id="bob", name="Other")


def test_update_member(svc: MemberService) -> None:
    svc.create(member_id="bob", name="Bob")
    updated = svc.update("bob", name="Bob Silva", email="bob@example.com")
    assert updated.name == "Bob Silva"
    assert updated.email == "bob@example.com"


def test_update_unknown_member_raises(svc: MemberService) -> None:
    with pytest.raises(MemberServiceError, match="not found"):
        svc.update("missing", name="X")


def test_inactivate_blocked_when_owns_active_portfolio(
    db: Database, svc: MemberService
) -> None:
    svc.create(member_id="bob", name="Bob")
    PortfolioRepository(db.connection).upsert(
        Portfolio(id="rv", name="RV", owner_id="bob", status="active")
    )
    with pytest.raises(MemberServiceError, match="still owns"):
        svc.inactivate("bob")


def test_inactivate_allowed_when_no_active_portfolio(
    db: Database, svc: MemberService
) -> None:
    svc.create(member_id="bob", name="Bob")
    PortfolioRepository(db.connection).upsert(
        Portfolio(id="rv", name="RV", owner_id="bob", status="archived")
    )
    member = svc.inactivate("bob")
    assert member.status == "inactive"


def test_activate_brings_member_back(svc: MemberService) -> None:
    svc.create(member_id="bob", name="Bob")
    svc.inactivate("bob")
    activated = svc.activate("bob")
    assert activated.status == "active"


def test_delete_blocked_when_owns_portfolios(
    db: Database, svc: MemberService
) -> None:
    svc.create(member_id="bob", name="Bob")
    PortfolioRepository(db.connection).upsert(
        Portfolio(id="rv", name="RV", owner_id="bob")
    )
    with pytest.raises(MemberServiceError, match="Cannot delete"):
        svc.delete("bob")


def test_list_portfolios_of(db: Database, svc: MemberService) -> None:
    svc.create(member_id="bob", name="Bob")
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", owner_id="bob"))
    p_repo.upsert(Portfolio(id="rf", name="RF", owner_id="bob"))
    portfolios = svc.list_portfolios_of("bob")
    assert {p.id for p in portfolios} == {"rv", "rf"}


def test_list_portfolios_of_missing_member(svc: MemberService) -> None:
    with pytest.raises(MemberServiceError, match="not found"):
        svc.list_portfolios_of("missing")


def test_dataclass_defaults() -> None:
    m = Member(id="x", name="X")
    assert m.status == "active"
    assert m.email is None
    assert m.display_name is None
