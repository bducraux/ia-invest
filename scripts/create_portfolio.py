"""Create a new portfolio folder from templates.

Layout (since the Members feature):

    portfolios/
      <owner-id>/
        <portfolio-id>/
          portfolio.yml
          inbox/  staging/  processed/  rejected/  exports/

Usage::

    python scripts/create_portfolio.py
    python scripts/create_portfolio.py --owner bruno --type renda-fixa --name "Renda Fixa"
    python scripts/create_portfolio.py --owner bruno --type renda-variavel --name "Acoes"
    python scripts/create_portfolio.py --templates-root /path/to/templates
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from storage.repository.db import Database
from storage.repository.members import MemberRepository

_DEFAULT_TEMPLATES_ROOT = Path(__file__).parent.parent / "templates"
_PORTFOLIOS_DIR = Path("portfolios")
_DEFAULT_DB_PATH = Path("ia_invest.db")
_GENERIC_TYPE = "generic"
_REQUIRED_SUBDIRS = ("inbox", "staging", "processed", "rejected", "exports")


# ---------------------------------------------------------------------- helpers

def _discover_template_dirs(templates_root: Path) -> dict[str, Path]:
    if not templates_root.exists() or not templates_root.is_dir():
        raise FileNotFoundError(f"Templates root not found: {templates_root}")

    templates: dict[str, Path] = {}
    for child in sorted(templates_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "portfolio.yml").exists():
            templates[child.name] = child
    return templates


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError("Value must contain at least one valid character.")
    return slug


def _prompt(label: str) -> str:
    while True:
        raw = input(f"{label}: ").strip()
        if raw:
            return raw
        print("Please provide a non-empty value.")


def _prompt_choice(prompt_text: str, options: list[str]) -> str:
    print(prompt_text)
    for idx, option in enumerate(options, start=1):
        print(f"  {idx}. {option}")

    while True:
        choice = input("Type number: ").strip()
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue
        index = int(choice)
        if 1 <= index <= len(options):
            return options[index - 1]
        print(f"Please choose a number between 1 and {len(options)}.")


def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    with manifest_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False, allow_unicode=True)


def _create_runtime_dirs(portfolio_dir: Path) -> None:
    for subdir in _REQUIRED_SUBDIRS:
        (portfolio_dir / subdir).mkdir(parents=True, exist_ok=True)


def _build_generic_manifest(
    *, portfolio_id: str, portfolio_name: str, owner_id: str, description: str | None
) -> dict[str, Any]:
    return {
        "id": portfolio_id,
        "name": portfolio_name,
        "description": description or "Portfolio de investimentos",
        "base_currency": "BRL",
        "status": "active",
        "owner_id": owner_id,
        "rules": {"allowed_asset_types": []},
        "sources": [],
        "import": {
            "move_processed_files": True,
            "deduplicate_by": [
                "source",
                "external_id",
                "operation_date",
                "asset_code",
                "operation_type",
            ],
        },
    }


def _load_template_manifest(template_dir: Path) -> dict[str, Any]:
    manifest_template = template_dir / "portfolio.yml"
    if not manifest_template.exists():
        raise FileNotFoundError(f"Template manifest not found: {manifest_template}")
    with manifest_template.open(encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh) or {})


# ---------------------------------------------------------------- main API

def create_portfolio(
    portfolio_name: str,
    *,
    portfolio_type: str,
    owner_id: str,
    templates_root: Path = _DEFAULT_TEMPLATES_ROOT,
    portfolios_dir: Path = _PORTFOLIOS_DIR,
    description: str | None = None,
) -> Path:
    """Create the on-disk portfolio folder and manifest. Returns the new dir."""
    templates = _discover_template_dirs(templates_root)
    known_types = [_GENERIC_TYPE, *templates.keys()]
    if portfolio_type not in known_types:
        raise ValueError(
            f"Unknown portfolio type '{portfolio_type}'. "
            f"Available: {', '.join(known_types)}"
        )

    if not owner_id:
        raise ValueError("owner_id is required to create a portfolio.")

    portfolio_id = _slugify(portfolio_name)
    owner_dir = portfolios_dir / owner_id
    target_dir = owner_dir / portfolio_id

    if target_dir.exists():
        raise FileExistsError(f"Target portfolio already exists: {target_dir}")

    owner_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=False)

    if portfolio_type == _GENERIC_TYPE:
        manifest = _build_generic_manifest(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_name,
            owner_id=owner_id,
            description=description,
        )
    else:
        manifest = _load_template_manifest(templates[portfolio_type])
        manifest["id"] = portfolio_id
        manifest["name"] = portfolio_name
        manifest["owner_id"] = owner_id
        if description is not None:
            manifest["description"] = description

    _write_manifest(target_dir / "portfolio.yml", manifest)
    _create_runtime_dirs(target_dir)
    return target_dir


# ------------------------------------------------------------------- CLI

def _resolve_owner(member_repo: MemberRepository, value: str | None) -> str:
    """Resolve the owner the user wants from the active members in the DB."""
    active = member_repo.list_active()
    if not active:
        print(
            "ERROR: no active members found in the database.\n"
            "       Create one first with: python scripts/create_member.py "
            "--name 'Bruno'",
            file=sys.stderr,
        )
        sys.exit(2)

    if value:
        member = member_repo.get_by_id_or_name(value)
        if member is None:
            print(
                f"ERROR: member '{value}' not found. Active members: "
                f"{', '.join(m.id for m in active)}",
                file=sys.stderr,
            )
            sys.exit(2)
        return member.id

    options = [f"{m.id}  ({m.name})" for m in active]
    chosen = _prompt_choice("Choose owner:", options)
    return active[options.index(chosen)].id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a portfolio directory from templates."
    )
    parser.add_argument("--owner", help="Member id or name that owns the portfolio.")
    parser.add_argument("--name", help="Portfolio display name.")
    parser.add_argument(
        "--type",
        dest="portfolio_type",
        help="Portfolio type/template (renda-variavel, renda-fixa, cripto, generic, ...).",
    )
    parser.add_argument("--description", help="Optional portfolio description override.")
    parser.add_argument(
        "--templates-root",
        default=str(_DEFAULT_TEMPLATES_ROOT),
        help=f"Root directory with portfolio templates (default: {_DEFAULT_TEMPLATES_ROOT}).",
    )
    parser.add_argument(
        "--portfolios-dir",
        default=str(_PORTFOLIOS_DIR),
        help=f"Root directory for created portfolios (default: {_PORTFOLIOS_DIR}).",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite database (default: {_DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    portfolio_name = args.name.strip() if args.name else _prompt("Portfolio name")

    templates_root = Path(args.templates_root)
    portfolios_dir = Path(args.portfolios_dir)

    with Database(Path(args.db)) as db:
        db.initialize()
        owner_id = _resolve_owner(MemberRepository(db.connection), args.owner)

    portfolio_type = args.portfolio_type
    if not portfolio_type:
        templates = _discover_template_dirs(templates_root)
        portfolio_type = _prompt_choice(
            "Choose portfolio type:",
            [_GENERIC_TYPE, *sorted(templates.keys())],
        )

    created_dir = create_portfolio(
        portfolio_name,
        portfolio_type=portfolio_type,
        owner_id=owner_id,
        templates_root=templates_root,
        portfolios_dir=portfolios_dir,
        description=args.description,
    )
    print(
        f"Portfolio created: {created_dir}  "
        f"(type: {portfolio_type}, owner: {owner_id})"
    )


if __name__ == "__main__":
    main()
