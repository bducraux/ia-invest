"""Database connection and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_DB_PATH = Path("ia_invest.db")
_SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


class Database:
    """Manages a single SQLite connection for the IA-Invest application.

    Usage::

        db = Database()          # uses default path
        db.initialize()          # applies schema if needed
        conn = db.connection     # raw sqlite3.Connection

    The connection is configured with:
    - WAL journal mode for better concurrent read performance.
    - Foreign key enforcement.
    - Row factory returning sqlite3.Row (dict-like access by column name).
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """Apply schema.sql if the database has not been initialised yet."""
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        self.connection.executescript(schema_sql)
        self.connection.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
