"""List all members and their portfolio counts.

Usage::

    python scripts/list_members.py
    python scripts/list_members.py --all          # include inactive
"""

from __future__ import annotations

import argparse
from pathlib import Path

from storage.repository.db import Database
from storage.repository.members import MemberRepository

_DEFAULT_DB_PATH = Path("ia_invest.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="List members.")
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {_DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include inactive members.",
    )
    args = parser.parse_args()

    with Database(Path(args.db)) as db:
        db.initialize()
        repo = MemberRepository(db.connection)
        members = repo.list_all() if args.all else repo.list_active()

        if not members:
            print("(no members)")
            return

        # Header
        print(f"{'ID':<24} {'NAME':<30} {'EMAIL':<32} {'STATUS':<10} {'PORTFOLIOS':>10}")
        print("-" * 110)
        for m in members:
            count = repo.count_portfolios(m.id)
            print(
                f"{m.id:<24} {m.name:<30} {(m.email or '-'):<32} "
                f"{m.status:<10} {count:>10}"
            )


if __name__ == "__main__":
    main()
