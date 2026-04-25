"""Unit tests for ``domain.performance_service``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.performance_service import (
    CdiAccumulation,
    PortfolioPerformanceService,
    compound_cdi,
)
from domain.position_valuation_service import ValuedPosition


def _vp(
    *,
    asset: str = "ITSA4",
    qty: float = 1000,
    avg_price: int = 850,
    total_cost: int = 850_000,
    current_price: int | None = 920,
    current_value: int | None = 920_000,
    unrealized: int | None = 70_000,
) -> ValuedPosition:
    return ValuedPosition(
        portfolio_id="p",
        asset_code=asset,
        asset_type="stock",
        asset_name=asset,
        quantity=qty,
        avg_price_cents=avg_price,
        total_cost_cents=total_cost,
        current_price_cents=current_price,
        current_value_cents=current_value,
        unrealized_pnl_cents=unrealized,
        unrealized_pnl_pct=None,
        quote_source="stub",
        quote_age_seconds=0,
        quote_status="live",
        quote_fetched_at=None,
    )


def test_lifetime_metrics_with_full_quotes() -> None:
    # Cost basis 8 500.00; market value 9 200.00; lifetime div 200.00.
    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        [_vp()],
        lifetime_dividends_cents=20_000,
        period_dividends_cents=20_000,
        period_months=12,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        cdi=None,
    )
    t = payload["totals"]
    assert t["total_cost_cents"] == 850_000
    assert t["current_value_cents"] == 920_000
    assert t["unrealized_pnl_cents"] == 70_000
    # Capital return 70 000 / 850 000 ≈ 0.0824
    assert t["lifetime_capital_return_pct"] == 0.0824
    # Income 20 000 / 850 000 ≈ 0.0235
    assert t["lifetime_income_return_pct"] == 0.0235
    # Total = 70_000 + 20_000 = 90_000 / 850_000 ≈ 0.1059
    assert t["lifetime_total_return_pct"] == 0.1059
    assert payload["period"]["dividends_received_cents"] == 20_000
    assert payload["period"]["cdi_accumulated_pct"] is None


def test_metrics_when_no_position_has_quote() -> None:
    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        [_vp(current_price=None, current_value=None, unrealized=None)],
        lifetime_dividends_cents=20_000,
        period_dividends_cents=0,
        period_months=12,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        cdi=None,
    )
    t = payload["totals"]
    assert t["current_value_cents"] is None
    assert t["unrealized_pnl_cents"] is None
    # Capital return falls back to 0/cost.
    assert t["lifetime_capital_return_pct"] == 0.0
    # Income still computable.
    assert t["lifetime_income_return_pct"] == 0.0235
    codes = {w["code"] for w in payload["warnings"]}
    assert "missing_quotes" in codes


def test_negative_quantity_positions_are_skipped() -> None:
    """Historical-data-gap positions are excluded from the totals."""
    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        [_vp(qty=-50, total_cost=-50_000)],
        lifetime_dividends_cents=0,
        period_dividends_cents=0,
        period_months=12,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        cdi=None,
    )
    t = payload["totals"]
    assert t["total_cost_cents"] == 0
    assert t["current_value_cents"] is None


def test_cdi_accumulation_block_flows_through() -> None:
    cdi = CdiAccumulation(
        accumulated_pct=0.1100,
        business_days=252,
        coverage_complete=True,
        missing_days=0,
    )
    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        [_vp()],
        lifetime_dividends_cents=0,
        period_dividends_cents=0,
        period_months=12,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        cdi=cdi,
    )
    p = payload["period"]
    assert p["cdi_accumulated_pct"] == 0.1100
    assert p["cdi_business_days"] == 252
    assert all(w["code"] != "cdi_partial_series" for w in payload["warnings"])


def test_cdi_partial_series_emits_warning() -> None:
    cdi = CdiAccumulation(
        accumulated_pct=0.05,
        business_days=120,
        coverage_complete=False,
        missing_days=15,
    )
    payload = PortfolioPerformanceService().aggregate_with_lifetime_dividends(
        [_vp()],
        lifetime_dividends_cents=0,
        period_dividends_cents=0,
        period_months=12,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        cdi=cdi,
    )
    codes = {w["code"] for w in payload["warnings"]}
    assert "cdi_partial_series" in codes


def test_aggregate_rejects_invalid_window() -> None:
    svc = PortfolioPerformanceService()
    with pytest.raises(ValueError):
        svc.aggregate_with_lifetime_dividends(
            [],
            lifetime_dividends_cents=0,
            period_dividends_cents=0,
            period_months=0,
            period_start=date(2025, 4, 26),
            period_end=date(2026, 4, 25),
            cdi=None,
        )
    with pytest.raises(ValueError):
        svc.aggregate_with_lifetime_dividends(
            [],
            lifetime_dividends_cents=0,
            period_dividends_cents=0,
            period_months=12,
            period_start=date(2026, 4, 25),
            period_end=date(2025, 4, 25),
            cdi=None,
        )


def test_compound_cdi_uses_decimal_factor_product() -> None:
    # Two days at 0.05 and 0.05 → (1.05)^2 - 1 = 0.1025.
    rates = {
        date(2025, 4, 21): Decimal("0.05"),
        date(2025, 4, 22): Decimal("0.05"),
    }
    acc = compound_cdi(rates)
    assert acc.business_days == 2
    assert acc.accumulated_pct == 0.1025
    assert acc.coverage_complete is True
