"""Tests for the Database class and schema initialisation."""

from __future__ import annotations

from pathlib import Path

from storage.repository.db import Database


def test_initialize_creates_tables(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.initialize()
    tables = [
        row[0]
        for row in db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    assert "portfolios" in tables
    assert "operations" in tables
    assert "positions" in tables
    assert "import_jobs" in tables
    assert "import_errors" in tables
    assert "schema_migrations" in tables
    db.close()


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    for _ in range(3):
        db = Database(db_path)
        db.initialize()
        db.close()


def test_row_factory_returns_dict_like(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.initialize()
    row = db.connection.execute(
        "SELECT version FROM schema_migrations LIMIT 1"
    ).fetchone()
    assert row["version"] == "0001"
    db.close()


def test_context_manager_closes_connection(tmp_path: Path) -> None:
    with Database(tmp_path / "test.db") as db:
        db.initialize()
        assert db.connection is not None
    assert db._conn is None
