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
        # Wait longer before failing when another process holds a write lock.
        # FastAPI sync endpoints may execute dependency setup and handler logic
        # in different worker threads; allow cross-thread connection access.
        conn = sqlite3.connect(self._db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """Apply schema.sql only when the database appears uninitialised."""
        if self._is_initialized():
            return

        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        self.connection.executescript(schema_sql)
        self.connection.commit()

    def _is_initialized(self) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'portfolios'
            LIMIT 1
            """
        ).fetchone()
        return row is not None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
