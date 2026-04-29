"""Tests for PortfolioService."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from domain.portfolio_service import PortfolioService


@pytest.fixture
def svc() -> PortfolioService:
    return PortfolioService()


@pytest.fixture
def valid_manifest(tmp_path: Path) -> Path:
    config = {
        "id": "renda-variavel",
        "name": "Renda Variável",
        "base_currency": "BRL",
        "status": "active",
        "owner_id": "default",
        "rules": {"allowed_asset_types": ["stock", "fii"]},
    }
    f = tmp_path / "portfolio.yml"
    f.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return f


def test_load_valid_manifest(svc: PortfolioService, valid_manifest: Path) -> None:
    portfolio = svc.load_from_yaml(valid_manifest)
    assert portfolio.id == "renda-variavel"
    assert portfolio.name == "Renda Variável"
    assert portfolio.base_currency == "BRL"
    assert portfolio.status == "active"
    assert portfolio.owner_id == "default"


def test_load_nonexistent_manifest_raises(svc: PortfolioService, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        svc.load_from_yaml(tmp_path / "nonexistent.yml")


def test_load_missing_required_field_raises(svc: PortfolioService, tmp_path: Path) -> None:
    config = {
        "name": "Missing ID",
        "base_currency": "BRL",
        "status": "active",
        "owner_id": "default",
    }
    f = tmp_path / "portfolio.yml"
    f.write_text(yaml.dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="id"):
        svc.load_from_yaml(f)


def test_load_missing_owner_raises(svc: PortfolioService, tmp_path: Path) -> None:
    config = {"id": "p1", "name": "P1", "base_currency": "BRL", "status": "active"}
    f = tmp_path / "portfolio.yml"
    f.write_text(yaml.dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="owner_id"):
        svc.load_from_yaml(f)


def test_load_invalid_status_raises(svc: PortfolioService, tmp_path: Path) -> None:
    config = {
        "id": "p1",
        "name": "P1",
        "base_currency": "BRL",
        "status": "unknown_status",
        "owner_id": "default",
    }
    f = tmp_path / "portfolio.yml"
    f.write_text(yaml.dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        svc.load_from_yaml(f)


def test_validate_asset_type_allowed(svc: PortfolioService, valid_manifest: Path) -> None:
    portfolio = svc.load_from_yaml(valid_manifest)
    assert svc.validate_asset_type(portfolio, "stock") is True
    assert svc.validate_asset_type(portfolio, "fii") is True


def test_validate_asset_type_not_allowed(svc: PortfolioService, valid_manifest: Path) -> None:
    portfolio = svc.load_from_yaml(valid_manifest)
    assert svc.validate_asset_type(portfolio, "crypto") is False


def test_validate_asset_type_no_restrictions(svc: PortfolioService, tmp_path: Path) -> None:
    config = {
        "id": "p1",
        "name": "P1",
        "base_currency": "BRL",
        "status": "active",
        "owner_id": "default",
    }
    f = tmp_path / "portfolio.yml"
    f.write_text(yaml.dump(config), encoding="utf-8")
    portfolio = svc.load_from_yaml(f)
    # No allowed_asset_types means no restriction
    assert svc.validate_asset_type(portfolio, "crypto") is True
