"""Initialise the IA-Invest database.

Applies storage/schema.sql to create all tables if they do not already exist.

Usage::

    python scripts/init_db.py [--db path/to/ia_invest.db]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.repository.db import Database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the IA-Invest SQLite database.")
    parser.add_argument(
        "--db",
        default="ia_invest.db",
        help="Path to the SQLite database file (default: ia_invest.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    print(f"Initialising database at: {db_path.resolve()}")

    with Database(db_path) as db:
        db.initialize()

    print("Database initialised successfully.")


if __name__ == "__main__":
    main()
