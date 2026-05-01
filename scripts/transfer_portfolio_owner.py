"""Transfer a portfolio to a different owner (member).

Performs an atomic operation: rename the on-disk directory from
``portfolios/<old-owner>/<portfolio-id>/`` to
``portfolios/<new-owner>/<portfolio-id>/``, then update the manifest
``owner_id`` and the ``portfolios.owner_id`` row in SQLite.

If the database update fails after the directory has already moved, the
directory is moved back so the filesystem and the database stay in sync.

Usage::

    python scripts/transfer_portfolio_owner.py --portfolio rv --to alice
    python scripts/transfer_portfolio_owner.py --portfolio rv --to alice --owner bob
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Any

import yaml

from domain.portfolio_service import PortfolioService
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository

_PORTFOLIOS_DIR = Path("portfolios")
_DEFAULT_DB_PATH = Path("ia_invest.db")


# ---------------------------------------------------------------- helpers

def _find_existing_dir(portfolio_id: str, owner_hint: str | None) -> tuple[Path, str]:
    """Return (current_dir, current_owner_id) for a portfolio, searching the
    new layout first then falling back to the legacy single-level layout.
    """
    if owner_hint:
        candidate = _PORTFOLIOS_DIR / owner_hint / portfolio_id
        if candidate.exists():
            return candidate, owner_hint

    if _PORTFOLIOS_DIR.exists():
        for owner_dir in _PORTFOLIOS_DIR.iterdir():
            if not owner_dir.is_dir():
                continue
            cand = owner_dir / portfolio_id
            if (cand / "portfolio.yml").exists():
                return cand, owner_dir.name

    legacy = _PORTFOLIOS_DIR / portfolio_id
    if (legacy / "portfolio.yml").exists():
        # Legacy: there is no owner directory to derive from; load it from
        # the manifest itself.
        with (legacy / "portfolio.yml").open(encoding="utf-8") as fh:
            cfg: dict[str, Any] = yaml.safe_load(fh) or {}
        return legacy, str(cfg.get("owner_id") or "default")

    raise FileNotFoundError(
        f"Portfolio '{portfolio_id}' not found under {_PORTFOLIOS_DIR}/"
    )


def _rewrite_manifest_owner(manifest_path: Path, new_owner_id: str) -> str:
    """Update owner_id in the YAML manifest. Returns the previous value."""
    with manifest_path.open(encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh) or {}
    previous = str(cfg.get("owner_id") or "")
    cfg["owner_id"] = new_owner_id
    with manifest_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
    return previous


# ---------------------------------------------------------------- main op

def transfer_portfolio_owner(
    portfolio_id: str,
    new_owner_id: str,
    *,
    db_path: Path = _DEFAULT_DB_PATH,
    portfolios_dir: Path = _PORTFOLIOS_DIR,
    owner_hint: str | None = None,
) -> Path:
    """Atomically move portfolio ownership in DB + filesystem.

    Returns the new directory path.  Raises ValueError on validation problems.
    """
    global _PORTFOLIOS_DIR
    _PORTFOLIOS_DIR = portfolios_dir  # local override for _find_existing_dir

    current_dir, current_owner_id = _find_existing_dir(portfolio_id, owner_hint)

    if current_owner_id == new_owner_id:
        # Nothing to do — both sides already agree.
        return current_dir

    new_owner_dir = portfolios_dir / new_owner_id
    target_dir = new_owner_dir / portfolio_id
    if target_dir.exists():
        raise FileExistsError(
            f"Target directory already exists: {target_dir}. Aborting transfer."
        )

    new_owner_dir.mkdir(parents=True, exist_ok=True)

    # Step 1 — move directory
    current_dir.rename(target_dir)
    moved = True
    try:
        # Step 2 — update manifest
        _rewrite_manifest_owner(target_dir / "portfolio.yml", new_owner_id)

        # Step 3 — update DB
        with Database(db_path) as db:
            db.initialize()
            members = MemberRepository(db.connection)
            portfolios = PortfolioRepository(db.connection)
            if members.get(new_owner_id) is None:
                raise ValueError(
                    f"Member '{new_owner_id}' does not exist. "
                    "Create it first with scripts/create_member.py."
                )
            svc = PortfolioService(
                portfolio_repo=portfolios, member_repo=members
            )
            # The portfolio row may not exist yet if the user has never run
            # `import_portfolio`; in that case we just persist it.
            if portfolios.get(portfolio_id) is None:
                from domain.models import Portfolio

                portfolios.upsert(
                    Portfolio(
                        id=portfolio_id,
                        name=portfolio_id,
                        owner_id=new_owner_id,
                    )
                )
            else:
                svc.transfer_ownership(portfolio_id, new_owner_id)
    except Exception:
        # Roll back the filesystem move on any failure during step 2 or 3.
        if moved and target_dir.exists():
            with contextlib.suppress(OSError):
                target_dir.rename(current_dir)
            # Restore manifest owner_id only if it was changed
            with contextlib.suppress(Exception):
                _rewrite_manifest_owner(
                    current_dir / "portfolio.yml", current_owner_id
                )
        raise

    return target_dir


# ------------------------------------------------------------------- CLI

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transfer a portfolio to a different owner."
    )
    parser.add_argument("--portfolio", required=True, help="Portfolio id.")
    parser.add_argument("--to", dest="new_owner", required=True, help="New owner id.")
    parser.add_argument(
        "--owner",
        default=None,
        help="Optional: hint of the current owner id (folder name).",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {_DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    try:
        target_dir = transfer_portfolio_owner(
            args.portfolio,
            args.new_owner,
            db_path=Path(args.db),
            owner_hint=args.owner,
        )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"Portfolio '{args.portfolio}' transferred to '{args.new_owner}': {target_dir}")


if __name__ == "__main__":
    main()
