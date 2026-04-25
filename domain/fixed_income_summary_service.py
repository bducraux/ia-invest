"""Fixed-income (renda fixa) summary service.

Pure-domain aggregation over a list of pre-valued
:class:`~domain.fixed_income.FixedIncomeValuation` objects. The service
does not touch the database, the BACEN cache, or the clock — its caller
is responsible for loading positions, building valuations and supplying
``today`` so the maturity ladder is deterministic in tests.

The output combines:

* **Aggregate totals** — principal applied vs current gross/net values,
  total estimated IR, accumulated income.
* **Maturity ladder** — buckets ``<=30d``, ``31-90d``, ``91-365d`` and
  ``>365d`` measured in calendar days from ``today``. Already-matured
  positions land in a separate ``matured`` block so they are not mixed
  into "active" allocation.
* **Per-position rows** — kept for the consumer to render a table.

All monetary fields are integer cents (BRL). ``estimated_ir_current_brl``
is reported as a positive number (the amount that would be withheld on
redemption today) and is **not** subtracted again from
``net_value_total_cents`` here — that already happened inside the
valuation service.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from domain.fixed_income import FixedIncomePosition, FixedIncomeValuation

_PCT_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class ValuedFixedIncomePosition:
    """Pair of contract + recomputed valuation for the summary service."""

    position: FixedIncomePosition
    valuation: FixedIncomeValuation


def _format_pct(value: Decimal) -> float:
    return float(value.quantize(_PCT_QUANT, rounding=ROUND_HALF_EVEN))


def _safe_pct(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return _format_pct(Decimal(numer) / Decimal(denom))


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _bucket(days_to_maturity: int) -> str:
    if days_to_maturity <= 30:
        return "le_30d"
    if days_to_maturity <= 90:
        return "le_90d"
    if days_to_maturity <= 365:
        return "le_365d"
    return "gt_365d"


_BUCKETS: tuple[str, ...] = ("le_30d", "le_90d", "le_365d", "gt_365d")


class FixedIncomeSummaryService:
    """Aggregate per-position valuations into a portfolio-level summary."""

    def summarise(
        self,
        valued: Iterable[ValuedFixedIncomePosition],
        *,
        as_of: date,
    ) -> dict[str, Any]:
        active_principal = 0
        active_gross = 0
        active_net = 0
        active_ir = 0
        matured_principal = 0
        matured_gross = 0
        matured_net = 0
        matured_ir = 0
        incomplete: list[dict[str, Any]] = []

        ladder: dict[str, dict[str, Any]] = {
            b: {
                "bucket": b,
                "count": 0,
                "principal_cents": 0,
                "gross_value_cents": 0,
                "net_value_cents": 0,
            }
            for b in _BUCKETS
        }

        rows: list[dict[str, Any]] = []
        upcoming: list[dict[str, Any]] = []

        for entry in valued:
            position = entry.position
            valuation = entry.valuation

            maturity = _parse_date(position.maturity_date)
            days_to_maturity = (maturity - as_of).days
            is_matured = days_to_maturity < 0 or position.status == "MATURED"

            if not valuation.is_complete:
                incomplete.append(
                    {
                        "position_id": position.id,
                        "asset_type": position.asset_type,
                        "product_name": position.product_name,
                        "reason": valuation.incomplete_reason,
                    }
                )

            row = {
                "position_id": position.id,
                "institution": position.institution,
                "asset_type": position.asset_type,
                "product_name": position.product_name,
                "remuneration_type": position.remuneration_type,
                "benchmark": position.benchmark,
                "benchmark_percent": position.benchmark_percent,
                "fixed_rate_annual_percent": position.fixed_rate_annual_percent,
                "application_date": position.application_date,
                "maturity_date": position.maturity_date,
                "days_to_maturity": days_to_maturity,
                "status": "MATURED" if is_matured else position.status,
                "principal_applied_cents": int(position.principal_applied_brl),
                "gross_value_cents": int(valuation.gross_value_current_brl),
                "estimated_ir_cents": int(valuation.estimated_ir_current_brl),
                "net_value_cents": int(valuation.net_value_current_brl),
                "tax_bracket_current": valuation.tax_bracket_current,
                "is_complete": bool(valuation.is_complete),
            }
            rows.append(row)

            if is_matured:
                matured_principal += int(position.principal_applied_brl)
                matured_gross += int(valuation.gross_value_current_brl)
                matured_net += int(valuation.net_value_current_brl)
                matured_ir += int(valuation.estimated_ir_current_brl)
                continue

            active_principal += int(position.principal_applied_brl)
            active_gross += int(valuation.gross_value_current_brl)
            active_net += int(valuation.net_value_current_brl)
            active_ir += int(valuation.estimated_ir_current_brl)

            bucket = ladder[_bucket(days_to_maturity)]
            bucket["count"] += 1
            bucket["principal_cents"] += int(position.principal_applied_brl)
            bucket["gross_value_cents"] += int(valuation.gross_value_current_brl)
            bucket["net_value_cents"] += int(valuation.net_value_current_brl)

            if days_to_maturity <= 30:
                upcoming.append(
                    {
                        "position_id": position.id,
                        "product_name": position.product_name,
                        "maturity_date": position.maturity_date,
                        "days_to_maturity": days_to_maturity,
                        "net_value_cents": int(valuation.net_value_current_brl),
                    }
                )

        upcoming.sort(key=lambda r: (r["days_to_maturity"], r["product_name"]))

        return {
            "as_of": as_of.isoformat(),
            "active_totals": {
                "count": sum(b["count"] for b in ladder.values()),
                "principal_cents": active_principal,
                "gross_value_cents": active_gross,
                "estimated_ir_cents": active_ir,
                "net_value_cents": active_net,
                "income_pct": _safe_pct(active_net - active_principal, active_principal),
            },
            "matured_totals": {
                "principal_cents": matured_principal,
                "gross_value_cents": matured_gross,
                "estimated_ir_cents": matured_ir,
                "net_value_cents": matured_net,
            },
            "maturity_ladder": list(ladder.values()),
            "upcoming_maturities": upcoming,
            "positions": rows,
            "incomplete_valuations": incomplete,
        }


__all__ = [
    "FixedIncomeSummaryService",
    "ValuedFixedIncomePosition",
]
