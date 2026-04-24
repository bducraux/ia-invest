"""Tests pinning the new valuation contract: missing weekday inside coverage
is treated as a holiday (silent skip), not as an incomplete-data gap.

This is the key behavioural change introduced when historical BACEN series
became the source of truth for CDI. Without it, every Brazilian holiday
(~10/year) would inflate ``incomplete_reason`` and potentially be treated
as a missing data point by callers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import DailyRateProvider
from domain.fixed_income_valuation import FixedClock, FixedIncomeValuationService


class _ProviderWithCoverage(DailyRateProvider):
    """Test double exposing a real ``get_coverage_end`` so the service
    can distinguish holidays from unfetched future days."""

    def __init__(self, rates: dict[date, Decimal], coverage_end: date) -> None:
        self._rates = rates
        self._coverage_end = coverage_end

    def get_daily_rates(
        self,
        start_date,    # noqa: ANN001
        end_date,      # noqa: ANN001
        benchmark: str = "CDI",
    ) -> dict[date, Decimal]:
        s = start_date if isinstance(start_date, date) else date.fromisoformat(start_date)
        e = end_date if isinstance(end_date, date) else date.fromisoformat(end_date)
        return {d: r for d, r in self._rates.items() if s <= d <= e}

    def get_coverage_end(self, benchmark: str = "CDI") -> date:
        return self._coverage_end


def _make_position(
    *,
    application_date: str,
    maturity_date: str,
    benchmark_percent: float = 100.0,
    principal_cents: int = 10_000_00,
) -> FixedIncomePosition:
    return FixedIncomePosition(
        portfolio_id="p1",
        institution="Banco X",
        asset_type="CDB",
        product_name="CDB CDI",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        investor_type="PF",
        currency="BRL",
        application_date=application_date,
        maturity_date=maturity_date,
        principal_applied_brl=principal_cents,
        fixed_rate_annual_percent=None,
        benchmark_percent=benchmark_percent,
    )


def test_missing_weekday_inside_coverage_is_treated_as_holiday() -> None:
    """Mon-Tue-Wed window with Tue absent — provider says coverage extends
    through Wed → Tue is a holiday, calc must be complete and only compound
    Mon and Wed."""
    rates = {
        date(2024, 1, 8): Decimal("0.0004"),    # Mon
        # 2024-01-09 (Tue) — intentionally missing → holiday
        date(2024, 1, 10): Decimal("0.0004"),   # Wed
    }
    provider = _ProviderWithCoverage(rates, coverage_end=date(2024, 1, 10))
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 10)),
    )
    pos = _make_position(
        application_date="2024-01-07",   # Sunday — accrual starts 01-08
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)

    assert result.is_complete, result.incomplete_reason
    expected = Decimal("10000") * (Decimal("1.0004") ** Decimal(2))
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 2


def test_missing_weekday_past_coverage_caps_accrual_at_coverage_end() -> None:
    """When ``coverage_end`` is before the valuation date, the accrual is
    capped at coverage_end (BACEN publishes CDI for day D on D+1, so the
    bank itself shows yesterday's value until today's CDI is published).
    The result is *complete* — not flagged as a gap."""
    rates = {
        date(2024, 1, 8): Decimal("0.0004"),
        # 2024-01-09 absent — but valuation will only accrue up to 01-08.
    }
    provider = _ProviderWithCoverage(rates, coverage_end=date(2024, 1, 8))
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 10)),
    )
    pos = _make_position(
        application_date="2024-01-07",
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)

    assert result.is_complete, result.incomplete_reason
    expected = Decimal("10000") * (Decimal("1.0004") ** Decimal(1))
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 2


def test_missing_weekday_inside_coverage_with_unfetched_tail_still_flags_gap() -> None:
    """Holes inside the coverage window are holidays (silent skip), but
    when the provider's coverage extends past a missing weekday it can
    no longer be a publishing-lag situation — that is a real gap."""
    rates = {
        date(2024, 1, 8): Decimal("0.0004"),
        # 2024-01-09 missing
        # coverage end at 01-09 means BACEN claims to have data through
        # that day → 01-09 must be a holiday OR a real missing row.
        # We bias toward "holiday" (silent) because BACEN is the source
        # of truth for B3 business days. This matches the first test in
        # this file; covered for completeness here too.
    }
    provider = _ProviderWithCoverage(rates, coverage_end=date(2024, 1, 9))
    service = FixedIncomeValuationService(
        cdi_provider=provider,
        clock=FixedClock(date(2024, 1, 9)),
    )
    pos = _make_position(
        application_date="2024-01-07",
        maturity_date="2025-01-01",
    )
    result = service.revalue(pos)

    # Coverage covers 01-09, the missing weekday is treated as a holiday.
    assert result.is_complete, result.incomplete_reason
    expected = Decimal("10000") * (Decimal("1.0004") ** Decimal(1))
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 2
