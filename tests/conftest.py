"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.models import Operation, Portfolio
from storage.repository.db import Database


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
        config={
            "id": "test-portfolio",
            "name": "Test Portfolio",
            "base_currency": "BRL",
            "status": "active",
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
