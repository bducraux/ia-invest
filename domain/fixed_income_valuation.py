"""Valuation service for brazilian fixed-income applications (V1 MVP).

Responsibilities
----------------
Given a :class:`~domain.fixed_income.FixedIncomePosition` and a
"current date", compute:

* ``gross_value_current_brl``
* ``gross_income_current_brl``
* ``estimated_ir_current_brl``
* ``net_value_current_brl``
* the IR bracket that applies if redeemed today

Conventions and decisions
-------------------------
* All arithmetic is performed in :class:`~decimal.Decimal` with high
  precision. Final monetary outputs are rounded to **2 decimals
  (``ROUND_HALF_EVEN``)** at the boundary, then converted to integer
  cents to match the rest of the codebase.
* **Prefixed (PRE)** uses *calendar-day* compounding with the convention
  ``factor = (1 + i_a)^(days / 365)``. This is a simplification: many
  bank contracts use 252 business days. The convention is documented
  here and can be swapped out by changing ``_PRE_DAYS_IN_YEAR`` (or
  introducing a per-position field in a future iteration).
* **CDI %** accumulates on **business days only**, using the daily CDI
  series provided by a :class:`DailyRateProvider`. The position's
  ``benchmark_percent`` is applied to each daily rate as
  ``effective_daily = (1 + cdi_daily) ** (benchmark_percent / 100) - 1``,
  which is the standard "X% do CDI" convention used by brazilian banks
  (X% of the *index*, applied multiplicatively per business day).
* Calculation is **always** clamped to the position lifetime
  ``[application_date, min(today, maturity_date)]``. After maturity
  the gross value is frozen at the maturity-day calculation.
* If the CDI series is incomplete for the period, the service returns
  ``is_complete=False`` together with a clear ``incomplete_reason``
  message — it never silently uses zeros.
* IOF is **not** applied (V1 product decision). See
  :mod:`domain.fixed_income_tax`.

This service is fully *pure*: it does not touch the database. The
caller is responsible for persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from typing import Protocol

from domain.fixed_income import FixedIncomePosition, FixedIncomeValuation
from domain.fixed_income_rates import DailyRateProvider
from domain.fixed_income_tax import FixedIncomeTaxService

# Use a comfortable precision for compounding over thousands of days.
getcontext().prec = 40

#: Day-count convention for prefixed CDB/LCI/LCA in the V1 MVP.
#: Brazilian bank-like products often use 252 business days; we use 365
#: calendar days as a simpler MVP convention. Documented and easy to
#: change in a future iteration.
_PRE_DAYS_IN_YEAR: Decimal = Decimal("365")


class Clock(Protocol):
    """Injectable clock so tests can pin "today" to a specific date."""

    def today(self) -> date: ...


class SystemClock:
    """Default clock returning the real system date."""

    def today(self) -> date:
        return date.today()


@dataclass
class FixedClock:
    """Clock that always returns the same configured date."""

    pinned: date

    def today(self) -> date:
        return self.pinned


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_cents(value: Decimal) -> int:
    """Round a BRL Decimal to 2 places and return integer cents.

    Uses banker's rounding (``ROUND_HALF_EVEN``) to be neutral over
    long series. This is the single rounding boundary in the pipeline.
    """
    quantised = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return int(quantised * 100)


class FixedIncomeValuationService:
    """Recalculate the gross/net value of a fixed-income position."""

    def __init__(
        self,
        cdi_provider: DailyRateProvider | None = None,
        tax_service: FixedIncomeTaxService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._cdi_provider = cdi_provider
        self._tax = tax_service or FixedIncomeTaxService()
        self._clock = clock or SystemClock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def revalue(self, position: FixedIncomePosition) -> FixedIncomeValuation:
        """Recompute valuation for a position against the configured clock."""
        application = _parse_date(position.application_date)
        maturity = _parse_date(position.maturity_date)
        today = self._clock.today()
        # Cap at maturity: after maturity, value is frozen at maturity day.
        valuation_day = min(today, maturity)

        if valuation_day < application:
            # Position not yet started — return principal as-is.
            return self._build_result(
                position,
                valuation_day=valuation_day,
                days_since_application=0,
                gross_value=Decimal(position.principal_applied_brl) / Decimal(100),
                is_complete=True,
                incomplete_reason=None,
            )

        days_since_application = (valuation_day - application).days

        principal = Decimal(position.principal_applied_brl) / Decimal(100)

        if position.remuneration_type == "PRE":
            gross_value = self._compute_pre(
                principal=principal,
                annual_rate_percent=position.fixed_rate_annual_percent or 0.0,
                days=days_since_application,
            )
            return self._build_result(
                position,
                valuation_day=valuation_day,
                days_since_application=days_since_application,
                gross_value=gross_value,
                is_complete=True,
                incomplete_reason=None,
            )

        if position.remuneration_type == "CDI_PERCENT":
            gross_value, complete, reason = self._compute_cdi_percent(
                principal=principal,
                benchmark_percent=position.benchmark_percent or 0.0,
                start=application,
                end=valuation_day,
            )
            return self._build_result(
                position,
                valuation_day=valuation_day,
                days_since_application=days_since_application,
                gross_value=gross_value,
                is_complete=complete,
                incomplete_reason=reason,
            )

        # __post_init__ on the dataclass should have rejected anything
        # else, but we guard explicitly:
        raise ValueError(f"Unsupported remuneration_type: {position.remuneration_type!r}")

    # ------------------------------------------------------------------
    # Internals — calculation primitives
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_pre(
        *,
        principal: Decimal,
        annual_rate_percent: float,
        days: int,
    ) -> Decimal:
        """Compounded prefixed value: P * (1 + i_a)^(days / 365)."""
        if days <= 0:
            return principal
        rate = Decimal(str(annual_rate_percent)) / Decimal(100)
        exponent = Decimal(days) / _PRE_DAYS_IN_YEAR
        # Decimal lacks a native non-integer power; use the standard
        # exp(ln(x) * y) identity with the high-precision context.
        base = Decimal(1) + rate
        factor = (base.ln() * exponent).exp()
        return principal * factor

    def _compute_cdi_percent(
        self,
        *,
        principal: Decimal,
        benchmark_percent: float,
        start: date,
        end: date,
    ) -> tuple[Decimal, bool, str | None]:
        """Compound CDI percent over business days between ``start`` and ``end``.

        ``start`` and ``end`` are inclusive on the *application* side and
        exclusive on the *end* side (we accrue rates for each business
        day **strictly after** the application date and up to and
        including the day before the valuation, matching how brazilian
        banks publish daily CDI). The caller is responsible for clamping
        ``end`` to maturity.
        """
        if end <= start:
            return principal, True, None

        if self._cdi_provider is None:
            return principal, False, "CDI rate provider not configured"

        # Apply CDI for accrual dates ``d`` such that
        # ``application_date < d <= valuation_day``.
        accrual_start = start + timedelta(days=1)
        rates = self._cdi_provider.get_daily_rates(accrual_start, end, benchmark="CDI")

        # Detect missing business days inside the window. We treat
        # Mon..Fri as business candidates and rely on the provider to
        # exclude bank holidays — when a candidate day has no rate, the
        # calculation is flagged incomplete.
        missing: list[date] = []
        cursor = accrual_start
        one_day = timedelta(days=1)
        while cursor <= end:
            if cursor.weekday() < 5 and cursor not in rates:
                missing.append(cursor)
            cursor += one_day

        if missing:
            sample = ", ".join(d.isoformat() for d in missing[:3])
            more = "" if len(missing) <= 3 else f" (+{len(missing) - 3} more)"
            return (
                principal,
                False,
                f"Missing CDI rates for {len(missing)} business day(s): {sample}{more}",
            )

        # Daily multiplier per "X% do CDI": (1 + cdi_d) ** (X/100) - 1.
        pct = Decimal(str(benchmark_percent)) / Decimal(100)
        accumulated = Decimal(1)
        for _, daily_rate in sorted(rates.items()):
            base = Decimal(1) + daily_rate
            # base ** pct using ln/exp for non-integer exponents.
            factor = (base.ln() * pct).exp()
            accumulated *= factor

        return principal * accumulated, True, None

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _build_result(
        self,
        position: FixedIncomePosition,
        *,
        valuation_day: date,
        days_since_application: int,
        gross_value: Decimal,
        is_complete: bool,
        incomplete_reason: str | None,
    ) -> FixedIncomeValuation:
        principal = Decimal(position.principal_applied_brl) / Decimal(100)
        gross_income = max(Decimal(0), gross_value - principal)

        if is_complete:
            ir_amount = self._tax.calculate_estimated_ir(
                position.asset_type,
                position.investor_type,
                days_since_application,
                gross_income,
            )
        else:
            ir_amount = Decimal(0)

        # The IR bracket label only depends on (asset_type, investor_type,
        # days). It is always meaningful — even when the gross calculation
        # is flagged incomplete — so users still see "isento" for LCI/LCA.
        try:
            ir_label: str | None = self._tax.get_ir_rate(
                position.asset_type,
                position.investor_type,
                max(days_since_application, 0),
            ).label
        except ValueError:
            ir_label = None

        net_value = gross_value - ir_amount

        return FixedIncomeValuation(
            position_id=position.id,
            valuation_date=valuation_day.isoformat(),
            days_since_application=days_since_application,
            gross_value_current_brl=_to_cents(gross_value),
            gross_income_current_brl=_to_cents(gross_income),
            estimated_ir_current_brl=_to_cents(ir_amount),
            net_value_current_brl=_to_cents(net_value),
            tax_bracket_current=ir_label,
            is_complete=is_complete,
            incomplete_reason=incomplete_reason,
        )
