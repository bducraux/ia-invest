"""Tests for scripts/transfer_portfolio_owner.py — atomic move + DB update."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from domain.members import Member
from domain.models import Portfolio
from scripts.transfer_portfolio_owner import transfer_portfolio_owner
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


_MANIFEST = """
id: rv
name: RV
base_currency: BRL
status: active
owner_id: bruno
""".strip() + "\n"


def _setup_filesystem(tmp_path: Path, owner: str = "bruno") -> Path:
    portfolios_dir = tmp_path / "portfolios"
    portfolio_dir = portfolios_dir / owner / "rv"
    portfolio_dir.mkdir(parents=True)
    (portfolio_dir / "portfolio.yml").write_text(_MANIFEST, encoding="utf-8")
    (portfolio_dir / "inbox").mkdir()
    return portfolios_dir


def _seed_db(db_path: Path, owners: list[str], portfolio_owner: str) -> None:
    with Database(db_path) as db:
        db.initialize()
        m_repo = MemberRepository(db.connection)
        for o in owners:
            m_repo.upsert(Member(id=o, name=o.title()))
        PortfolioRepository(db.connection).upsert(
            Portfolio(id="rv", name="RV", owner_id=portfolio_owner)
        )


def test_transfer_moves_folder_and_updates_db(tmp_path: Path) -> None:
    portfolios_dir = _setup_filesystem(tmp_path)
    db_path = tmp_path / "ia.db"
    _seed_db(db_path, ["bruno", "rafa"], portfolio_owner="bruno")

    target = transfer_portfolio_owner(
        "rv", "rafa", db_path=db_path, portfolios_dir=portfolios_dir
    )

    assert target == portfolios_dir / "rafa" / "rv"
    assert (target / "portfolio.yml").exists()
    assert not (portfolios_dir / "bruno" / "rv").exists()

    # manifest updated
    cfg = yaml.safe_load((target / "portfolio.yml").read_text(encoding="utf-8"))
    assert cfg["owner_id"] == "rafa"

    # DB updated
    with Database(db_path) as db:
        portfolio = PortfolioRepository(db.connection).get("rv")
    assert portfolio is not None and portfolio.owner_id == "rafa"


def test_transfer_aborts_when_target_exists(tmp_path: Path) -> None:
    portfolios_dir = _setup_filesystem(tmp_path)
    # Pre-create a colliding directory
    (portfolios_dir / "rafa" / "rv").mkdir(parents=True)

    db_path = tmp_path / "ia.db"
    _seed_db(db_path, ["bruno", "rafa"], portfolio_owner="bruno")

    with pytest.raises(FileExistsError):
        transfer_portfolio_owner(
            "rv", "rafa", db_path=db_path, portfolios_dir=portfolios_dir
        )

    # Source still in place
    assert (portfolios_dir / "bruno" / "rv" / "portfolio.yml").exists()


def test_transfer_rolls_back_when_member_missing(tmp_path: Path) -> None:
    portfolios_dir = _setup_filesystem(tmp_path)
    db_path = tmp_path / "ia.db"
    _seed_db(db_path, ["bruno"], portfolio_owner="bruno")  # no 'rafa'

    with pytest.raises(ValueError, match="Member 'rafa'"):
        transfer_portfolio_owner(
            "rv", "rafa", db_path=db_path, portfolios_dir=portfolios_dir
        )

    # Filesystem is restored
    assert (portfolios_dir / "bruno" / "rv" / "portfolio.yml").exists()
    assert not (portfolios_dir / "rafa" / "rv").exists()
    cfg = yaml.safe_load(
        (portfolios_dir / "bruno" / "rv" / "portfolio.yml").read_text(encoding="utf-8")
    )
    assert cfg["owner_id"] == "bruno"


def test_transfer_no_op_when_already_owner(tmp_path: Path) -> None:
    portfolios_dir = _setup_filesystem(tmp_path)
    db_path = tmp_path / "ia.db"
    _seed_db(db_path, ["bruno"], portfolio_owner="bruno")

    target = transfer_portfolio_owner(
        "rv", "bruno", db_path=db_path, portfolios_dir=portfolios_dir
    )
    assert target == portfolios_dir / "bruno" / "rv"
