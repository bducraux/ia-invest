"""Bootstrap member rows from the on-disk `portfolios/` folder structure.

The new layout is `portfolios/<owner-id>/<portfolio-slug>/portfolio.yml`.
Each top-level subdirectory under `portfolios/` represents a member id.
This script idempotently creates a member row for every such directory that
contains at least one `portfolio.yml`, so a freshly initialised database is
not blocked by the `portfolios.owner_id REFERENCES members(id)` foreign key
when `import_all` runs immediately after `init_db`.

Existing members are left untouched; only missing ones are inserted with a
sensible default `name` derived from the directory name.

Usage::

    python scripts/bootstrap_members_from_fs.py
    python scripts/bootstrap_members_from_fs.py --portfolios-dir portfolios
    python scripts/bootstrap_members_from_fs.py --db ia_invest.db
"""

from __future__ import annotations

import argparse
from pathlib import Path

from domain.members import Member
from storage.repository.db import Database
from storage.repository.members import MemberRepository

_PORTFOLIOS_DIR = Path("portfolios")
_DEFAULT_DB_PATH = Path("ia_invest.db")


def _discover_owner_ids(portfolios_dir: Path) -> list[str]:
    """Return owner ids inferred from `portfolios/<owner>/<...>/portfolio.yml`."""
    if not portfolios_dir.exists():
        return []
    owners: list[str] = []
    for owner_dir in sorted(portfolios_dir.iterdir()):
        if not owner_dir.is_dir() or owner_dir.name.startswith("."):
            continue
        # Skip legacy single-level layout (portfolio.yml directly under owner_dir).
        if (owner_dir / "portfolio.yml").exists():
            continue
        # Only consider directories that hold at least one portfolio manifest.
        has_portfolio = any(
            child.is_dir() and (child / "portfolio.yml").exists()
            for child in owner_dir.iterdir()
        )
        if has_portfolio:
            owners.append(owner_dir.name)
    return owners


def bootstrap(portfolios_dir: Path, db_path: Path) -> tuple[int, int]:
    """Create missing members for each owner directory. Returns (created, skipped)."""
    owner_ids = _discover_owner_ids(portfolios_dir)
    if not owner_ids:
        return (0, 0)

    created = 0
    skipped = 0
    with Database(db_path) as db:
        db.initialize()
        repo = MemberRepository(db.connection)
        for owner_id in owner_ids:
            if repo.get(owner_id) is not None:
                skipped += 1
                continue
            display = owner_id.replace("-", " ").replace("_", " ").title()
            repo.upsert(Member(id=owner_id, name=display))
            created += 1
            print(f"  + member '{owner_id}' created")
    return (created, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create member rows from the portfolios/ folder layout."
    )
    parser.add_argument(
        "--portfolios-dir",
        default=str(_PORTFOLIOS_DIR),
        help=f"Root portfolios directory (default: {_PORTFOLIOS_DIR}).",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {_DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    created, skipped = bootstrap(Path(args.portfolios_dir), Path(args.db))
    print(f"Bootstrap done: {created} created, {skipped} already existed.")


if __name__ == "__main__":
    main()
