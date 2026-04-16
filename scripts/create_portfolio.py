"""Create a new portfolio folder from templates.

Usage::

    python scripts/create_portfolio.py
    python scripts/create_portfolio.py --name "Minha Carteira"
    python scripts/create_portfolio.py --type renda-variavel --name "Acoes"
    python scripts/create_portfolio.py --templates-root /path/to/templates
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_TEMPLATES_ROOT = Path(__file__).parent.parent / "templates"
_PORTFOLIOS_DIR = Path("portfolios")
_GENERIC_TYPE = "generic"
_REQUIRED_SUBDIRS = ("inbox", "staging", "processed", "rejected", "exports")


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


def _slugify_portfolio_id(name: str) -> str:
    portfolio_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower())
    portfolio_id = re.sub(r"-+", "-", portfolio_id).strip("-")
    if not portfolio_id:
        raise ValueError("Portfolio name must contain at least one valid character.")
    return portfolio_id


def _prompt_portfolio_name() -> str:
    while True:
        raw = input("Portfolio name: ").strip()
        if raw:
            return raw
        print("Please provide a non-empty portfolio name.")


def _prompt_portfolio_type(template_names: list[str]) -> str:
    options = [_GENERIC_TYPE, *template_names]
    print("Choose portfolio type:")
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


def _create_from_generic_template(
    target_dir: Path,
    *,
    portfolio_id: str,
    portfolio_name: str,
    description: str | None,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=False)
    for subdir in _REQUIRED_SUBDIRS:
        (target_dir / subdir).mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "id": portfolio_id,
        "name": portfolio_name,
        "description": description or "Portfolio de investimentos",
        "base_currency": "BRL",
        "status": "active",
        "rules": {
            "allowed_asset_types": [],
        },
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
    _write_manifest(target_dir / "portfolio.yml", manifest)


def _create_from_template_dir(
    template_dir: Path,
    target_dir: Path,
    *,
    portfolio_id: str,
    portfolio_name: str,
    description: str | None,
) -> None:
    manifest_template = template_dir / "portfolio.yml"
    if not manifest_template.exists():
        raise FileNotFoundError(f"Template manifest not found: {manifest_template}")

    shutil.copytree(template_dir, target_dir)

    manifest_path = target_dir / "portfolio.yml"
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    manifest["id"] = portfolio_id
    manifest["name"] = portfolio_name
    if description is not None:
        manifest["description"] = description

    _write_manifest(manifest_path, manifest)


def create_portfolio(
    portfolio_name: str,
    *,
    portfolio_type: str,
    templates_root: Path = _DEFAULT_TEMPLATES_ROOT,
    portfolios_dir: Path = _PORTFOLIOS_DIR,
    description: str | None = None,
) -> Path:
    templates = _discover_template_dirs(templates_root)
    known_types = [_GENERIC_TYPE, *templates.keys()]
    if portfolio_type not in known_types:
        raise ValueError(
            f"Unknown portfolio type '{portfolio_type}'. Available: {', '.join(known_types)}"
        )

    portfolio_id = _slugify_portfolio_id(portfolio_name)
    target_dir = portfolios_dir / portfolio_id

    if target_dir.exists():
        raise FileExistsError(f"Target portfolio already exists: {target_dir}")

    portfolios_dir.mkdir(parents=True, exist_ok=True)
    if portfolio_type == _GENERIC_TYPE:
        _create_from_generic_template(
            target_dir,
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_name,
            description=description,
        )
    else:
        _create_from_template_dir(
            templates[portfolio_type],
            target_dir,
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_name,
            description=description,
        )

    return target_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a portfolio directory from templates."
    )
    parser.add_argument(
        "--name",
        help="Portfolio display name. If omitted, asks interactively.",
    )
    parser.add_argument(
        "--type",
        dest="portfolio_type",
        help="Portfolio type/template to use (e.g. renda-variavel, renda-fixa, cripto, generic).",
    )
    parser.add_argument(
        "--description",
        help="Optional portfolio description override.",
    )
    parser.add_argument(
        "--templates-root",
        default=str(_DEFAULT_TEMPLATES_ROOT),
        help=(
            "Root directory with portfolio templates. "
            "Each subfolder containing portfolio.yml is a type. "
            f"(default: {_DEFAULT_TEMPLATES_ROOT})"
        ),
    )
    parser.add_argument(
        "--sample-dir",
        help=(
            "Deprecated. Use --type and --templates-root. "
            "If provided, this directory is used as a one-off custom template."
        ),
    )
    args = parser.parse_args()

    portfolio_name = args.name.strip() if args.name else _prompt_portfolio_name()

    portfolio_type = args.portfolio_type
    templates_root = Path(args.templates_root)

    if args.sample_dir:
        sample_dir = Path(args.sample_dir)
        if not sample_dir.exists() or not sample_dir.is_dir():
            raise FileNotFoundError(f"Sample directory not found: {sample_dir}")

        temp_type = sample_dir.name
        if not (sample_dir / "portfolio.yml").exists():
            raise FileNotFoundError(f"Template manifest not found: {sample_dir / 'portfolio.yml'}")

        portfolio_type = temp_type
        templates_root = sample_dir.parent

    if not portfolio_type:
        templates = _discover_template_dirs(templates_root)
        portfolio_type = _prompt_portfolio_type(sorted(templates.keys()))

    created_dir = create_portfolio(
        portfolio_name,
        portfolio_type=portfolio_type,
        templates_root=templates_root,
        description=args.description,
    )
    print(f"Portfolio created: {created_dir} (type: {portfolio_type})")


if __name__ == "__main__":
    main()