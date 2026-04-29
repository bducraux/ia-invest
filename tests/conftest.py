"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from domain.members import Member
from domain.models import Operation, Portfolio
from storage.repository.db import Database
from storage.repository.members import MemberRepository


@pytest.fixture(autouse=True)
def _seed_default_member() -> Iterator[None]:
    """Auto-seed a 'default' member on every Database.initialize() call.

    Many existing tests build their own SQLite database inline (without using
    the ``tmp_db`` fixture) and then upsert portfolios.  Now that
    ``portfolios.owner_id`` is a NOT NULL FK to ``members``, those upserts
    would fail.  We patch ``Database.initialize`` to also ensure a generic
    ``default`` member exists so the FK is always satisfiable in tests.
    Production code paths (``scripts/create_portfolio.py``) still require an
    explicit ``--owner`` value, so this only affects tests.
    """
    original_initialize = Database.initialize

    def patched_initialize(self: Database) -> None:
        original_initialize(self)
        try:
            MemberRepository(self.connection).upsert(
                Member(id="default", name="Default Member", status="active")
            )
        except Exception:  # noqa: BLE001
            # Be defensive: never break a test because the seed couldn't run.
            pass

    Database.initialize = patched_initialize  # type: ignore[method-assign]
    try:
        yield
    finally:
        Database.initialize = original_initialize  # type: ignore[method-assign]


@pytest.fixture
def tmp_db(tmp_path: Path) -> Database:
    """Provide an initialised in-memory-like Database backed by a temp file."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db


@pytest.fixture
def sample_portfolio() -> Portfolio:
    return Portfolio(
        id="test-portfolio",
        name="Test Portfolio",
        description="Portfolio for tests",
        base_currency="BRL",
        status="active",
        owner_id="default",
        config={
            "id": "test-portfolio",
            "name": "Test Portfolio",
            "base_currency": "BRL",
            "status": "active",
            "owner_id": "default",
            "rules": {"allowed_asset_types": ["stock", "fii", "etf", "crypto"]},
            "import": {
                "move_processed_files": False,
                "deduplicate_by": [
                    "source", "external_id", "operation_date", "asset_code", "operation_type"
                ],
            },
        },
    )


@pytest.fixture
def sample_operation(sample_portfolio: Portfolio) -> Operation:
    return Operation(
        portfolio_id=sample_portfolio.id,
        source="broker_csv",
        external_id="OP001",
        asset_code="PETR4",
        asset_type="stock",
        operation_type="buy",
        operation_date="2024-01-15",
        quantity=100.0,
        unit_price=3500,    # R$ 35.00
        gross_value=350000, # R$ 3500.00
        fees=150,           # R$ 1.50
    )
