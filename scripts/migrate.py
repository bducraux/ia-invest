"""Apply pending SQLite schema migrations from storage/migrations/.

Usage::

    python scripts/migrate.py [--db path/to/ia_invest.db]
    make migrate
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "storage" / "migrations"


def run_migrations(db_path: str | Path) -> int:
    """Apply any unapplied migrations. Returns the count applied."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # schema_migrations must already exist (created by init_db / schema.sql)
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations")
    }

    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    pending = [f for f in migration_files if f.stem[:4] not in applied]

    if not pending:
        print("No pending migrations.")
        conn.close()
        return 0

    for mf in pending:
        version = mf.stem[:4]
        print(f"Applying {version}: {mf.name} ... ", end="", flush=True)
        sql = mf.read_text(encoding="utf-8")
        # executescript() issues an implicit COMMIT before running, which is
        # correct here — each migration is its own atomic unit.
        conn.executescript(sql)
        print("done")

    conn.close()
    print(f"Applied {len(pending)} migration(s).")
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending IA-Invest DB migrations.")
    parser.add_argument("--db", default="ia_invest.db", help="Path to SQLite database")
    args = parser.parse_args()
    run_migrations(args.db)


if __name__ == "__main__":
    main()
