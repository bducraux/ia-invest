"""Create a new portfolio folder from a sample template.

Usage::

    python scripts/create_portfolio.py
    python scripts/create_portfolio.py --name "Minha Carteira"
    python scripts/create_portfolio.py --sample-dir /path/to/sample
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import yaml

_DEFAULT_SAMPLE_DIR = Path("/home/bruno/projects/portfolios/cripto")
_PORTFOLIOS_DIR = Path("portfolios")


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


def create_portfolio(
    portfolio_name: str,
    *,
    sample_dir: Path = _DEFAULT_SAMPLE_DIR,
    portfolios_dir: Path = _PORTFOLIOS_DIR,
) -> Path:
    if not sample_dir.exists() or not sample_dir.is_dir():
        raise FileNotFoundError(f"Sample directory not found: {sample_dir}")

    manifest_template = sample_dir / "portfolio.yml"
    if not manifest_template.exists():
        raise FileNotFoundError(f"Template manifest not found: {manifest_template}")

    portfolio_id = _slugify_portfolio_id(portfolio_name)
    target_dir = portfolios_dir / portfolio_id

    if target_dir.exists():
        raise FileExistsError(f"Target portfolio already exists: {target_dir}")

    portfolios_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(sample_dir, target_dir)

    manifest_path = target_dir / "portfolio.yml"
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    manifest["id"] = portfolio_id
    manifest["name"] = portfolio_name

    with manifest_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False, allow_unicode=True)

    return target_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a portfolio directory from a sample template."
    )
    parser.add_argument(
        "--name",
        help="Portfolio display name. If omitted, asks interactively.",
    )
    parser.add_argument(
        "--sample-dir",
        default=str(_DEFAULT_SAMPLE_DIR),
        help=(
            "Sample portfolio directory to copy from "
            f"(default: {_DEFAULT_SAMPLE_DIR})"
        ),
    )
    args = parser.parse_args()

    portfolio_name = args.name.strip() if args.name else _prompt_portfolio_name()

    created_dir = create_portfolio(
        portfolio_name,
        sample_dir=Path(args.sample_dir),
    )
    print(f"Portfolio created: {created_dir}")


if __name__ == "__main__":
    main()