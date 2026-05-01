"""Tests for PortfolioRepository, OperationRepository, PositionRepository."""

from __future__ import annotations

import pytest

from domain.models import Operation, Portfolio, Position
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


@pytest.fixture
def db(tmp_db: Database) -> Database:
    return tmp_db


def test_portfolio_upsert_and_get(db: Database) -> None:
    repo = PortfolioRepository(db.connection)
    p = Portfolio(id="rv", name="Renda Variável", base_currency="BRL", status="active")
    repo.upsert(p)
    result = repo.get("rv")
    assert result is not None
    assert result.id == "rv"
    assert result.name == "Renda Variável"


def test_portfolio_upsert_updates_existing(db: Database) -> None:
    repo = PortfolioRepository(db.connection)
    p = Portfolio(id="rv", name="Old Name", base_currency="BRL", status="active")
    repo.upsert(p)
    p2 = Portfolio(id="rv", name="New Name", base_currency="BRL", status="active")
    repo.upsert(p2)
    assert repo.get("rv").name == "New Name"  # type: ignore[union-attr]


def test_portfolio_list_active(db: Database) -> None:
    repo = PortfolioRepository(db.connection)
    repo.upsert(Portfolio(id="p1", name="P1", base_currency="BRL", status="active"))
    repo.upsert(Portfolio(id="p2", name="P2", base_currency="BRL", status="inactive"))
    active = repo.list_active()
    assert len(active) == 1
    assert active[0].id == "p1"


def test_operation_insert_many(db: Database) -> None:
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", base_currency="BRL", status="active"))

    op_repo = OperationRepository(db.connection)
    ops = [
        Operation(
            portfolio_id="rv",
            source="broker_csv",
            external_id=f"OP{i}",
            asset_code="PETR4",
            asset_type="stock",
            operation_type="buy",
            operation_date="2024-01-15",
            quantity=100.0,
            unit_price=3500,
            gross_value=350000,
        )
        for i in range(3)
    ]
    inserted, skipped = op_repo.insert_many(ops)
    assert inserted == 3
    assert skipped == 0


def test_operation_dedup_on_insert(db: Database) -> None:
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", base_currency="BRL", status="active"))

    op_repo = OperationRepository(db.connection)
    op = Operation(
        portfolio_id="rv",
        source="broker_csv",
        external_id="OP001",
        asset_code="PETR4",
        asset_type="stock",
        operation_type="buy",
        operation_date="2024-01-15",
        quantity=100.0,
        unit_price=3500,
        gross_value=350000,
    )
    op_repo.insert_many([op])
    inserted, skipped = op_repo.insert_many([op])  # duplicate
    assert inserted == 0
    assert skipped == 1


def test_operation_list_all_by_portfolio_returns_full_history(db: Database) -> None:
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", base_currency="BRL", status="active"))

    op_repo = OperationRepository(db.connection)
    ops = [
        Operation(
            portfolio_id="rv",
            source="broker_csv",
            external_id=f"OP{i}",
            asset_code="PETR4",
            asset_type="stock",
            operation_type="buy",
            operation_date="2024-01-15",
            quantity=1.0,
            unit_price=100,
            gross_value=100,
        )
        for i in range(600)
    ]
    inserted, skipped = op_repo.insert_many(ops)
    assert inserted == 600
    assert skipped == 0

    paged = op_repo.list_by_portfolio("rv")
    full = op_repo.list_all_by_portfolio("rv")

    assert len(paged) == 500
    assert len(full) == 600


def test_position_upsert_and_get(db: Database) -> None:
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", base_currency="BRL", status="active"))

    pos_repo = PositionRepository(db.connection)
    pos = Position(
        portfolio_id="rv",
        asset_code="PETR4",
        asset_type="stock",
        quantity=100.0,
        avg_price=3500,
        total_cost=350000,
    )
    pos_repo.upsert(pos)
    result = pos_repo.get("rv", "PETR4")
    assert result is not None
    assert result.quantity == 100.0
    assert result.avg_price == 3500


def test_position_list_open(db: Database) -> None:
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", base_currency="BRL", status="active"))

    pos_repo = PositionRepository(db.connection)
    pos_repo.upsert(Position(
        portfolio_id="rv", asset_code="PETR4", asset_type="stock", quantity=100.0,
        avg_price=3500, total_cost=350000,
    ))
    pos_repo.upsert(Position(
        portfolio_id="rv", asset_code="VALE3", asset_type="stock", quantity=0.0,
        avg_price=7500, total_cost=0,
    ))
    open_positions = pos_repo.list_open_by_portfolio("rv")
    assert len(open_positions) == 1
    assert open_positions[0]["asset_code"] == "PETR4"


# ---------------------------------------------------------------------------
# Owner-related extensions to PortfolioRepository
# ---------------------------------------------------------------------------

def test_portfolio_list_by_owner(db: Database) -> None:
    from domain.members import Member
    from storage.repository.members import MemberRepository

    MemberRepository(db.connection).upsert(Member(id="bob", name="Bob"))
    MemberRepository(db.connection).upsert(Member(id="alice", name="Alice"))
    repo = PortfolioRepository(db.connection)
    repo.upsert(Portfolio(id="rv-bob", name="RV", owner_id="bob"))
    repo.upsert(Portfolio(id="rf-bob", name="RF", owner_id="bob"))
    repo.upsert(Portfolio(id="rv-alice", name="RV", owner_id="alice"))

    bob_pids = [p.id for p in repo.list_by_owner("bob")]
    assert bob_pids == ["rf-bob", "rv-bob"]
    assert [p.id for p in repo.list_by_owner("alice")] == ["rv-alice"]
    assert repo.list_by_owner("missing") == []


def test_portfolio_transfer_ownership(db: Database) -> None:
    from domain.members import Member
    from storage.repository.members import MemberRepository

    MemberRepository(db.connection).upsert(Member(id="bob", name="Bob"))
    MemberRepository(db.connection).upsert(Member(id="alice", name="Alice"))
    repo = PortfolioRepository(db.connection)
    repo.upsert(Portfolio(id="rv", name="RV", owner_id="bob"))

    repo.transfer_ownership("rv", "alice")
    got = repo.get("rv")
    assert got is not None and got.owner_id == "alice"


def test_portfolio_transfer_ownership_unknown_member(db: Database) -> None:
    from domain.members import Member
    from storage.repository.members import MemberRepository

    MemberRepository(db.connection).upsert(Member(id="bob", name="Bob"))
    repo = PortfolioRepository(db.connection)
    repo.upsert(Portfolio(id="rv", name="RV", owner_id="bob"))

    with pytest.raises(ValueError, match="Member 'ghost' not found"):
        repo.transfer_ownership("rv", "ghost")


def test_portfolio_owner_id_required_at_db_level(db: Database) -> None:
    """Schema enforces NOT NULL on owner_id."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.connection.execute(
            "INSERT INTO portfolios (id, name, base_currency, status) "
            "VALUES ('x', 'X', 'BRL', 'active')"
        )
