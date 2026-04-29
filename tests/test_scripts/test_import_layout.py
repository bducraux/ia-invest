"""Tests for the new portfolios/<owner>/<pid>/ layout in import_portfolio."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import import_portfolio as import_portfolio_module


_MINIMAL_MANIFEST = """
id: rv-test
name: RV Test
base_currency: BRL
status: active
owner_id: bruno
rules:
  allowed_asset_types:
    - stock
sources:
  - type: broker_csv
    enabled: true
import:
  move_processed_files: true
""".strip() + "\n"


def _setup_portfolio(tmp_path: Path, owner: str, manifest: str) -> Path:
    portfolios_dir = tmp_path / "portfolios"
    portfolio_dir = portfolios_dir / owner / "rv-test"
    portfolio_dir.mkdir(parents=True)
    (portfolio_dir / "portfolio.yml").write_text(manifest, encoding="utf-8")
    (portfolio_dir / "inbox").mkdir()
    return portfolios_dir


def test_finds_portfolio_in_owner_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolios_dir = _setup_portfolio(tmp_path, "bruno", _MINIMAL_MANIFEST)
    monkeypatch.setattr(import_portfolio_module, "_PORTFOLIOS_DIR", portfolios_dir)

    db_path = tmp_path / "ia.db"
    result = import_portfolio_module.import_portfolio(
        "rv-test", db_path=db_path, owner_id="bruno"
    )
    # Empty inbox => 0 files processed but no error.
    assert "error" not in result
    assert result["files_processed"] == 0


def test_explicit_owner_must_match_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolios_dir = _setup_portfolio(tmp_path, "bruno", _MINIMAL_MANIFEST)
    monkeypatch.setattr(import_portfolio_module, "_PORTFOLIOS_DIR", portfolios_dir)

    db_path = tmp_path / "ia.db"
    result = import_portfolio_module.import_portfolio(
        "rv-test", db_path=db_path, owner_id="rafa"
    )
    assert "error" in result
    assert "not found" in result["error"]


def test_owner_id_in_manifest_must_match_parent_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Manifest declares owner_id=bruno but the file lives under rafa/.
    bad_manifest = _MINIMAL_MANIFEST.replace("owner_id: bruno", "owner_id: rafa")
    portfolios_dir = _setup_portfolio(tmp_path, "bruno", bad_manifest)
    monkeypatch.setattr(import_portfolio_module, "_PORTFOLIOS_DIR", portfolios_dir)

    db_path = tmp_path / "ia.db"
    result = import_portfolio_module.import_portfolio("rv-test", db_path=db_path)
    assert "error" in result
    assert "Owner mismatch" in result["error"]


def test_missing_portfolio_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        import_portfolio_module, "_PORTFOLIOS_DIR", tmp_path / "portfolios"
    )
    result = import_portfolio_module.import_portfolio(
        "nonexistent", db_path=tmp_path / "ia.db"
    )
    assert "error" in result
