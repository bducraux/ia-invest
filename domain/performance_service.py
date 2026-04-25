"""Portfolio performance service.

Computes simple, *honest* return metrics that can be derived from the data
the codebase actually persists (positions, operations, cached quotes,
BACEN daily benchmarks). The service does **not** attempt time-weighted
or money-weighted return — those require periodic position snapshots that
IA-Invest does not store.

What it produces, and why
-------------------------
* **Lifetime metrics** — capital, income and total return measured over the
  whole life of every position, divided by the total cost basis. These are
  always available because they only need the current market value, the
  stored ``total_cost`` and the lifetime ``dividends`` already maintained
  by :class:`~domain.position_service.PositionService`.
* **Period metrics** — dividends received in the requested window plus the
  CDI accumulated over the same window (compounded daily-rate series from
  ``daily_benchmark_rates``). The CDI block is omitted with a warning when
  the BACEN cache does not cover the full window.

All monetary values are integer cents and percentages are decimal
fractions (``0.10`` = 10%) per the project convention.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from domain.position_valuation_service import ValuedPosition

_PCT_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class CdiAccumulation:
    """CDI compounded over a window from the daily series."""

    accumulated_pct: float
    business_days: int
    coverage_complete: bool
    missing_days: int


def _format_pct(value: Decimal) -> float:
    return float(value.quantize(_PCT_QUANT, rounding=ROUND_HALF_EVEN))


def _safe_pct(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return _format_pct(Decimal(numer) / Decimal(denom))


class PortfolioPerformanceService:
    """Aggregate per-position valuations into portfolio-level performance."""

    def aggregate_with_lifetime_dividends(
        self,
        valued_positions: Iterable[ValuedPosition],
        *,
        lifetime_dividends_cents: int,
        period_dividends_cents: int,
        period_months: int,
        period_start: date,
        period_end: date,
        cdi: CdiAccumulation | None,
        lifetime_realized_pnl_cents: int = 0,
    ) -> dict[str, Any]:
        """Convenience entry-point that accepts lifetime dividends explicitly.

        Preferred call from the tool layer; ``aggregate()`` is kept for
        symmetry with other services and treats lifetime dividends as zero.
        """
        if period_months < 1:
            raise ValueError(f"period_months must be >= 1 (got {period_months})")
        if period_end < period_start:
            raise ValueError(
                "period_end must be on or after period_start "
                f"(got {period_start.isoformat()} → {period_end.isoformat()})"
            )

        total_cost = 0
        total_value = 0
        total_unrealized = 0
        valued_count = 0
        unvalued_assets: list[str] = []

        for vp in valued_positions:
            if vp.quantity <= 0:
                continue
            total_cost += int(vp.total_cost_cents)
            if vp.current_value_cents is None:
                unvalued_assets.append(vp.asset_code)
                continue
            total_value += int(vp.current_value_cents)
            total_unrealized += int(vp.unrealized_pnl_cents or 0)
            valued_count += 1

        return self._finalise(
            total_cost=total_cost,
            total_value=total_value if valued_count else None,
            total_unrealized=total_unrealized if valued_count else None,
            lifetime_dividends=lifetime_dividends_cents,
            lifetime_realized_pnl=lifetime_realized_pnl_cents,
            period_dividends=period_dividends_cents,
            period_months=period_months,
            period_start=period_start,
            period_end=period_end,
            cdi=cdi,
            unvalued_assets=unvalued_assets,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _finalise(  # noqa: PLR0913 — clear keyword-only parameters
        self,
        *,
        total_cost: int,
        total_value: int | None,
        total_unrealized: int | None,
        lifetime_dividends: int,
        lifetime_realized_pnl: int,
        period_dividends: int,
        period_months: int,
        period_start: date,
        period_end: date,
        cdi: CdiAccumulation | None,
        unvalued_assets: list[str],
    ) -> dict[str, Any]:
        # Lifetime totals: when no position has a quote we cannot report a
        # current market value and total return collapses to dividends +
        # realised P&L over cost (still useful), so keep the breakdown.
        unrealized_for_total = total_unrealized or 0
        lifetime_total_return = (
            unrealized_for_total + lifetime_dividends + lifetime_realized_pnl
        )

        warnings: list[dict[str, Any]] = []
        if unvalued_assets:
            warnings.append(
                {
                    "code": "missing_quotes",
                    "message": (
                        "Sem cotação atual para os ativos abaixo; valores e "
                        "retorno de capital ignoraram esses ativos."
                    ),
                    "assets": sorted(unvalued_assets),
                }
            )
        if cdi is not None and not cdi.coverage_complete:
            warnings.append(
                {
                    "code": "cdi_partial_series",
                    "message": (
                        f"Série CDI incompleta para a janela ({cdi.missing_days} dias úteis sem dados)."
                    ),
                }
            )

        period_block: dict[str, Any] = {
            "months": period_months,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "dividends_received_cents": int(period_dividends),
            "cdi_accumulated_pct": cdi.accumulated_pct if cdi is not None else None,
            "cdi_business_days": cdi.business_days if cdi is not None else None,
        }

        return {
            "method": "simple_total_return_on_cost_basis",
            "totals": {
                "total_cost_cents": int(total_cost),
                "current_value_cents": total_value,
                "unrealized_pnl_cents": total_unrealized,
                "unrealized_pnl_pct": _safe_pct(total_unrealized or 0, total_cost),
                "lifetime_dividends_cents": int(lifetime_dividends),
                "lifetime_realized_pnl_cents": int(lifetime_realized_pnl),
                "lifetime_total_return_cents": int(lifetime_total_return),
                "lifetime_total_return_pct": _safe_pct(lifetime_total_return, total_cost),
                "lifetime_income_return_pct": _safe_pct(lifetime_dividends, total_cost),
                "lifetime_capital_return_pct": _safe_pct(unrealized_for_total, total_cost),
            },
            "period": period_block,
            "warnings": warnings,
        }


def compound_cdi(daily_rates: dict[date, Decimal]) -> CdiAccumulation:
    """Compound a CDI daily series into an accumulated rate.

    BACEN publishes business-day-only data; the accumulation is
    ``∏ (1 + r_d) - 1`` over every present day. ``coverage_complete`` is
    always ``True`` here because callers decide what "complete" means
    relative to a target window — the helper just compounds what was given.
    """
    factor = Decimal(1)
    for rate in daily_rates.values():
        factor *= Decimal(1) + Decimal(rate)
    accumulated = factor - Decimal(1)
    return CdiAccumulation(
        accumulated_pct=_format_pct(accumulated),
        business_days=len(daily_rates),
        coverage_complete=True,
        missing_days=0,
    )


__all__ = [
    "CdiAccumulation",
    "PortfolioPerformanceService",
    "compound_cdi",
]
