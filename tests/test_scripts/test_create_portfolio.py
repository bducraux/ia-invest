"""Tests for scripts/create_portfolio.py — new layout (portfolios/<owner>/<pid>/)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.create_portfolio import create_portfolio


def _write_minimal_template(root: Path, name: str, allowed: list[str]) -> None:
    template_dir = root / name
    template_dir.mkdir(parents=True)
    (template_dir / "portfolio.yml").write_text(
        yaml.safe_dump(
            {
                "id": name,
                "name": name.title(),
                "base_currency": "BRL",
                "status": "active",
                "owner_id": "default",
                "rules": {"allowed_asset_types": allowed},
                "sources": [],
                "import": {"move_processed_files": True, "deduplicate_by": []},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_create_portfolio_creates_owner_subfolder(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    portfolios = tmp_path / "portfolios"
    _write_minimal_template(templates, "renda-fixa", ["CDB", "LCI"])

    target = create_portfolio(
        "Minha Renda Fixa",
        portfolio_type="renda-fixa",
        owner_id="bruno",
        templates_root=templates,
        portfolios_dir=portfolios,
    )

    assert target == portfolios / "bruno" / "minha-renda-fixa"
    assert (target / "portfolio.yml").exists()
    for sub in ("inbox", "staging", "processed", "rejected", "exports"):
        assert (target / sub).is_dir()

    manifest = yaml.safe_load((target / "portfolio.yml").read_text(encoding="utf-8"))
    assert manifest["id"] == "minha-renda-fixa"
    assert manifest["name"] == "Minha Renda Fixa"
    assert manifest["owner_id"] == "bruno"


def test_create_portfolio_requires_owner(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    _write_minimal_template(templates, "renda-fixa", ["CDB"])
    with pytest.raises(ValueError, match="owner_id is required"):
        create_portfolio(
            "X",
            portfolio_type="renda-fixa",
            owner_id="",
            templates_root=templates,
            portfolios_dir=tmp_path / "portfolios",
        )


def test_create_portfolio_unknown_type(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    with pytest.raises(ValueError, match="Unknown portfolio type"):
        create_portfolio(
            "X",
            portfolio_type="does-not-exist",
            owner_id="bruno",
            templates_root=templates,
            portfolios_dir=tmp_path / "portfolios",
        )


def test_create_portfolio_existing_target_aborts(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    portfolios = tmp_path / "portfolios"
    _write_minimal_template(templates, "renda-fixa", ["CDB"])

    create_portfolio(
        "Carteira",
        portfolio_type="renda-fixa",
        owner_id="bruno",
        templates_root=templates,
        portfolios_dir=portfolios,
    )
    with pytest.raises(FileExistsError):
        create_portfolio(
            "Carteira",
            portfolio_type="renda-fixa",
            owner_id="bruno",
            templates_root=templates,
            portfolios_dir=portfolios,
        )


def test_create_portfolio_generic_type(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    portfolios = tmp_path / "portfolios"

    target = create_portfolio(
        "Misturada",
        portfolio_type="generic",
        owner_id="rafa",
        templates_root=templates,
        portfolios_dir=portfolios,
    )
    assert target == portfolios / "rafa" / "misturada"
    assert (target / "portfolio.yml").exists()
    manifest = yaml.safe_load((target / "portfolio.yml").read_text(encoding="utf-8"))
    assert manifest["owner_id"] == "rafa"
