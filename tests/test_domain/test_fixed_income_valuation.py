"""Tests for FixedIncomeValuationService — gross/net valuation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import FlatCDIRateProvider, InMemoryCDIRateProvider
from domain.fixed_income_valuation import (
    FixedClock,
    FixedIncomeValuationService,
)


def _make_position(
    *,
    asset_type: str = "CDB",
    remuneration_type: str = "PRE",
    benchmark: str = "NONE",
    fixed_rate: float | None = 12.0,
    benchmark_percent: float | None = None,
    application_date: str = "2023-01-02",
    maturity_date: str = "2026-01-02",
    principal_cents: int = 100_000_00,    # R$ 100,000.00
) -> FixedIncomePosition:
    return FixedIncomePosition(
        portfolio_id="p1",
        institution="Banco X",
        asset_type=asset_type,
        product_name=f"{asset_type} {remuneration_type}",
        remuneration_type=remuneration_type,
        benchmark=benchmark,
        investor_type="PF",
        currency="BRL",
        application_date=application_date,
        maturity_date=maturity_date,
        principal_applied_brl=principal_cents,
        fixed_rate_annual_percent=fixed_rate,
        benchmark_percent=benchmark_percent,
    )


# ---------------------------------------------------------------------------
# Prefixed (PRE)
# ---------------------------------------------------------------------------


def test_cdb_pre_one_year_uses_22_5_pct_bracket_when_under_180_days() -> None:
    # Application 100 days ago => 22.5% bracket.
    service = FixedIncomeValuationService(clock=FixedClock(date(2024, 4, 10)))
    pos = _make_position(
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        fixed_rate=10.0,
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    # 100 days at 10%/year compounded by 100/365.
    expected_factor = (Decimal("1.10") ** (Decimal(100) / Decimal(365)))
    expected_gross = Decimal("10000") * expected_factor
    expected_income = expected_gross - Decimal("10000")
    expected_ir = expected_income * Decimal("0.225")

    assert abs(result.gross_value_current_brl - int(round(expected_gross * 100))) <= 1
    assert abs(result.estimated_ir_current_brl - int(round(expected_ir * 100))) <= 1
    assert result.tax_bracket_current == "22.5%"


def test_cdb_pre_above_720_days_uses_15_pct_bracket() -> None:
    service = FixedIncomeValuationService(clock=FixedClock(date(2026, 1, 2)))
    pos = _make_position(
        application_date="2023-01-02",
        maturity_date="2030-01-02",
        fixed_rate=12.0,
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    assert result.tax_bracket_current == "15%"
    assert result.days_since_application > 720
    # IR amount should be 15% of gross income.
    expected_ir = (
        (Decimal(result.gross_value_current_brl) - Decimal(result.gross_income_current_brl) * 0)
        - Decimal(pos.principal_applied_brl)
    )
    expected_ir = (Decimal(result.gross_income_current_brl) * Decimal("0.15")).quantize(Decimal("1"))
    assert abs(result.estimated_ir_current_brl - int(expected_ir)) <= 1


@pytest.mark.parametrize("asset", ["LCI", "LCA"])
def test_lci_lca_pre_is_exempt(asset: str) -> None:
    service = FixedIncomeValuationService(clock=FixedClock(date(2024, 7, 1)))
    pos = _make_position(
        asset_type=asset,
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        fixed_rate=10.0,
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    assert result.estimated_ir_current_brl == 0
    assert result.net_value_current_brl == result.gross_value_current_brl
    assert result.tax_bracket_current == "isento"


def test_pre_value_does_not_grow_after_maturity() -> None:
    """After maturity, gross value is frozen at maturity-day calculation."""
    service = FixedIncomeValuationService(clock=FixedClock(date(2030, 6, 1)))
    pos = _make_position(
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        fixed_rate=10.0,
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    expected = Decimal("10000") * (
        Decimal("1.10") ** (Decimal(366) / Decimal(365))
    )    # 366 days (2024 leap)
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 1
    assert result.days_since_application == 366    # 2024 was leap year


# ---------------------------------------------------------------------------
# CDI %
# ---------------------------------------------------------------------------


def test_cdb_cdi_percent_with_fake_series_compounds_business_days() -> None:
    """100% of CDI at 0.04% per business day for 5 BD = (1.0004)^5 - 1."""
    provider = FlatCDIRateProvider("0.0004")
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 8)),    # Monday after 5 BDs
    )
    pos = _make_position(
        asset_type="CDB",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        benchmark_percent=100.0,
        fixed_rate=None,
        application_date="2024-01-01",   # Mon
        maturity_date="2025-01-01",
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    # Accrual window is 2024-01-02 .. 2024-01-08 inclusive = 5 BDs
    expected = Decimal("10000") * (Decimal("1.0004") ** Decimal(5))
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 2
    assert result.is_complete


def test_cdi_percent_with_factor_below_100_pct() -> None:
    provider = FlatCDIRateProvider("0.0004")
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 8)),
    )
    pos = _make_position(
        asset_type="LCI",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        benchmark_percent=90.0,
        fixed_rate=None,
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)

    pct = Decimal("0.9")
    daily_factor = (Decimal("1.0004").ln() * pct).exp()
    expected = Decimal("10000") * (daily_factor ** Decimal(5))
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 2
    # LCI/LCA exempt
    assert result.estimated_ir_current_brl == 0
    assert result.net_value_current_brl == result.gross_value_current_brl


@pytest.mark.parametrize("asset", ["LCA"])
def test_lca_cdi_percent_is_exempt(asset: str) -> None:
    provider = FlatCDIRateProvider("0.0004")
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 8)),
    )
    pos = _make_position(
        asset_type=asset,
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        benchmark_percent=100.0,
        fixed_rate=None,
        application_date="2024-01-01",
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)
    assert result.estimated_ir_current_brl == 0
    assert result.tax_bracket_current == "isento"


def test_cdi_percent_marks_incomplete_when_series_missing() -> None:
    # Provider only knows 2024-01-02; 03/04/05/08 are business days but missing.
    provider = InMemoryCDIRateProvider({"2024-01-02": "0.0004"})
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 8)),
    )
    pos = _make_position(
        asset_type="CDB",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        benchmark_percent=100.0,
        fixed_rate=None,
        application_date="2024-01-01",
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)
    assert not result.is_complete
    assert result.incomplete_reason and "Missing" in result.incomplete_reason


def test_cdi_percent_without_provider_marks_incomplete() -> None:
    service = FixedIncomeValuationService(
        cdi_provider=None, clock=FixedClock(date(2024, 1, 8))
    )
    pos = _make_position(
        asset_type="CDB",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        benchmark_percent=100.0,
        fixed_rate=None,
        application_date="2024-01-01",
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)
    assert not result.is_complete


# ---------------------------------------------------------------------------
# Clock & rounding
# ---------------------------------------------------------------------------


def test_clock_is_injectable_and_used_consistently() -> None:
    service = FixedIncomeValuationService(clock=FixedClock(date(2024, 6, 30)))
    pos = _make_position(
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        fixed_rate=10.0,
        principal_cents=10_000_00,
    )
    result = service.revalue(pos)
    # 2024-06-30 - 2024-01-01 = 181 days (2024 is leap year)
    assert result.days_since_application == 181
    assert result.valuation_date == "2024-06-30"


def test_monetary_rounding_returns_integer_cents() -> None:
    service = FixedIncomeValuationService(clock=FixedClock(date(2024, 4, 10)))
    pos = _make_position(
        application_date="2024-01-01",
        maturity_date="2025-01-01",
        fixed_rate=10.0,
        principal_cents=12_345_67,
    )
    result = service.revalue(pos)
    assert isinstance(result.gross_value_current_brl, int)
    assert isinstance(result.estimated_ir_current_brl, int)
    assert isinstance(result.net_value_current_brl, int)
    # net + ir == gross (no IOF in V1)
    assert result.net_value_current_brl + result.estimated_ir_current_brl == result.gross_value_current_brl
