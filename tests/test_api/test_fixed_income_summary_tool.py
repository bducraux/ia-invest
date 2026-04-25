"""Tests for the ``get_fixed_income_summary`` MCP tool."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import FlatCDIRateProvider
from domain.models import Portfolio
from mcp_server.tools.fixed_income_summary import get_fixed_income_summary
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.portfolios import PortfolioRepository


def _seed_portfolio(db: Database, pid: str = "renda-fixa") -> None:
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name=pid, base_currency="BRL")
    )


def _add_pre(
    db: Database, pid: str, *, principal: int, application: str, maturity: str,
    rate_pct: float = 13.0, product: str = "CDB PRE",
) -> int:
    repo = FixedIncomePositionRepository(db.connection)
    pos = FixedIncomePosition(
        portfolio_id=pid,
        institution="Banco X",
        asset_type="CDB",
        product_name=product,
        remuneration_type="PRE",
        benchmark="NONE",
        investor_type="PF",
        currency="BRL",
        application_date=application,
        maturity_date=maturity,
        principal_applied_brl=principal,
        fixed_rate_annual_percent=rate_pct,
    )
    return repo.insert(pos)


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    assert "error" in get_fixed_income_summary(tmp_db, "ghost")


def test_empty_portfolio_returns_zero_totals_and_buckets(tmp_db: Database) -> None:
    _seed_portfolio(tmp_db)
    result = get_fixed_income_summary(
        tmp_db, "renda-fixa", as_of=date(2026, 4, 25),
        cdi_provider=FlatCDIRateProvider(Decimal("0")),
    )
    assert result["active_totals"]["count"] == 0
    assert result["active_totals"]["principal_cents"] == 0
    assert all(b["count"] == 0 for b in result["maturity_ladder"])
    assert result["upcoming_maturities"] == []
    assert result["positions"] == []


def test_active_totals_aggregate_pre_positions(tmp_db: Database) -> None:
    pid = "renda-fixa"
    _seed_portfolio(tmp_db, pid)
    _add_pre(tmp_db, pid, principal=100_000, application="2024-04-25", maturity="2026-10-25")
    _add_pre(tmp_db, pid, principal=200_000, application="2024-04-25", maturity="2027-04-25")
    result = get_fixed_income_summary(
        tmp_db, pid, as_of=date(2026, 4, 25),
        cdi_provider=FlatCDIRateProvider(Decimal("0")),
    )
    a = result["active_totals"]
    assert a["count"] == 2
    assert a["principal_cents"] == 300_000
    # PRE compounded over 2 years at 13% → both gross > principal.
    assert a["gross_value_cents"] > a["principal_cents"]
    assert a["net_value_cents"] > 0
    assert a["estimated_ir_cents"] >= 0


def test_matured_positions_isolated_from_active(tmp_db: Database) -> None:
    pid = "renda-fixa"
    _seed_portfolio(tmp_db, pid)
    _add_pre(
        tmp_db, pid, principal=100_000,
        application="2024-04-25", maturity="2025-04-25",  # already matured
        product="CDB Vencido",
    )
    _add_pre(
        tmp_db, pid, principal=50_000,
        application="2024-04-25", maturity="2027-04-25",
        product="CDB Ativo",
    )
    result = get_fixed_income_summary(
        tmp_db, pid, as_of=date(2026, 4, 25),
        cdi_provider=FlatCDIRateProvider(Decimal("0")),
    )
    assert result["active_totals"]["count"] == 1
    assert result["active_totals"]["principal_cents"] == 50_000
    assert result["matured_totals"]["principal_cents"] == 100_000


def test_upcoming_maturities_window_is_30_days(tmp_db: Database) -> None:
    pid = "renda-fixa"
    _seed_portfolio(tmp_db, pid)
    _add_pre(
        tmp_db, pid, principal=10_000,
        application="2024-04-25", maturity="2026-05-10",  # ~15 days
        product="CDB Curto",
    )
    _add_pre(
        tmp_db, pid, principal=10_000,
        application="2024-04-25", maturity="2026-09-01",  # ~129 days
        product="CDB Longo",
    )
    result = get_fixed_income_summary(
        tmp_db, pid, as_of=date(2026, 4, 25),
        cdi_provider=FlatCDIRateProvider(Decimal("0")),
    )
    assert [u["product_name"] for u in result["upcoming_maturities"]] == ["CDB Curto"]
