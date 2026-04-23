"""Tests for FixedIncomePositionRepository — schema + persistence."""

from __future__ import annotations

import pytest

from domain.fixed_income import FixedIncomePosition
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.portfolios import PortfolioRepository


def _seed_portfolio(db: Database, sample_portfolio):
    PortfolioRepository(db.connection).upsert(sample_portfolio)


def _make() -> FixedIncomePosition:
    return FixedIncomePosition(
        portfolio_id="test-portfolio",
        institution="Banco X",
        asset_type="CDB",
        product_name="CDB Pre 12%",
        remuneration_type="PRE",
        benchmark="NONE",
        investor_type="PF",
        currency="BRL",
        application_date="2024-01-02",
        maturity_date="2026-01-02",
        principal_applied_brl=1_000_000,
        fixed_rate_annual_percent=12.0,
        liquidity_label="No vencimento",
        notes="seed",
    )


def test_insert_and_read_back_round_trips_all_fields(tmp_db: Database, sample_portfolio):
    _seed_portfolio(tmp_db, sample_portfolio)
    repo = FixedIncomePositionRepository(tmp_db.connection)

    pos = _make()
    new_id = repo.insert(pos)

    assert new_id > 0
    fetched = repo.get(new_id)
    assert fetched is not None
    assert fetched.institution == "Banco X"
    assert fetched.asset_type == "CDB"
    assert fetched.principal_applied_brl == 1_000_000
    assert fetched.fixed_rate_annual_percent == 12.0
    assert fetched.benchmark == "NONE"
    assert fetched.status == "ACTIVE"
    assert fetched.auto_reapply_enabled is False
    assert fetched.notes == "seed"


def test_list_by_portfolio_filters_correctly(tmp_db: Database, sample_portfolio):
    _seed_portfolio(tmp_db, sample_portfolio)
    repo = FixedIncomePositionRepository(tmp_db.connection)

    repo.insert(_make())
    matured = _make()
    matured.status = "MATURED"
    repo.insert(matured)

    assert len(repo.list_by_portfolio("test-portfolio")) == 2
    assert len(repo.list_by_portfolio("test-portfolio", status="ACTIVE")) == 1
    assert len(repo.list_by_portfolio("test-portfolio", status="MATURED")) == 1


def test_invalid_position_rejected_at_dataclass_level():
    with pytest.raises(ValueError):
        FixedIncomePosition(
            portfolio_id="p",
            institution="X",
            asset_type="CDB",
            product_name="CDB",
            remuneration_type="PRE",
            benchmark="NONE",
            investor_type="PF",
            currency="BRL",
            application_date="2024-01-01",
            maturity_date="2025-01-01",
            principal_applied_brl=1_000_000,
            fixed_rate_annual_percent=None,    # missing
        )


def test_delete_removes_position(tmp_db: Database, sample_portfolio):
    _seed_portfolio(tmp_db, sample_portfolio)
    repo = FixedIncomePositionRepository(tmp_db.connection)

    pos_id = repo.insert(_make())
    assert repo.get(pos_id) is not None

    repo.delete(pos_id, "test-portfolio")

    assert repo.get(pos_id) is None
    assert repo.list_by_portfolio("test-portfolio") == []
