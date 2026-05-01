"""Create a new family member (owner of one or more portfolios).

Usage::

    python scripts/create_member.py
    python scripts/create_member.py --id bob --name "Bob"
    python scripts/create_member.py --id alice --name "Alice" --email alice@example.com
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from domain.members import MemberService, MemberServiceError
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository

_DEFAULT_DB_PATH = Path("ia_invest.db")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _prompt(label: str, *, required: bool = True, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        if not required:
            return ""
        print(f"Please provide a non-empty value for {label}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new member.")
    parser.add_argument("--id", dest="member_id", help="Slug id (kebab-case).")
    parser.add_argument("--name", help="Display name (required).")
    parser.add_argument("--display-name", dest="display_name", default=None)
    parser.add_argument("--email", default=None, help="Optional unique email.")
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {_DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    name = args.name or _prompt("Member name")
    member_id = args.member_id or _slugify(_prompt("Member id (slug)", default=_slugify(name)))
    display_name = args.display_name
    email = args.email

    db_path = Path(args.db)
    with Database(db_path) as db:
        db.initialize()
        svc = MemberService(
            MemberRepository(db.connection),
            PortfolioRepository(db.connection),
        )
        try:
            member = svc.create(
                member_id=member_id,
                name=name,
                display_name=display_name,
                email=email,
            )
        except MemberServiceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)

    print(
        f"Member created: id='{member.id}' name='{member.name}' "
        f"email='{member.email or '-'}'"
    )


if __name__ == "__main__":
    main()
