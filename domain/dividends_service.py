"""Dividend aggregation service.

Pure-domain summarisation of provento operations (``dividend``, ``jcp``,
``rendimento``) into per-asset, per-month and per-type breakdowns. The
service does not touch the database directly: it consumes operation rows
already loaded by the caller. Money values are integer cents throughout to
match the rest of the codebase.

The "DY estimate" produced here is intentionally a *moving* dividend yield:
``sum(provento_cents in window) / current_portfolio_value_cents``. It is a
forward-looking-ish heuristic — not the official trailing-twelve-month DY
published by issuers — and is documented as such in the response payload.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

#: Operation types recognised as proventos by IA-Invest. Kept in sync with
#: ``domain/position_service.py`` (``_INCOME_TYPES``) and
#: ``normalizers/validator.py``. ``amortization`` is intentionally excluded:
#: it is a return-of-principal event and not a yield component.
PROVENT_TYPES: frozenset[str] = frozenset({"dividend", "jcp", "rendimento"})


@dataclass(frozen=True)
class DividendEvent:
    """A single provento event as surfaced in the per-asset breakdown."""

    operation_date: str  # ISO YYYY-MM-DD
    operation_type: str
    amount_cents: int


@dataclass
class _AssetBucket:
    asset_code: str
    asset_name: str | None = None
    total_cents: int = 0
    events: list[DividendEvent] = field(default_factory=list)


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _amount_cents(row: dict[str, Any]) -> int:
    """Return the proventum amount in cents for an operation row.

    Brokers often record proventos with both ``gross_value`` and ``net_value``
    populated; the gross figure is what the agent should report (IR for JCP
    is handled at year-end declaration, not at the event level).
    """
    gross = row.get("gross_value")
    if gross is not None:
        try:
            return int(gross)
        except (TypeError, ValueError):
            pass
    net = row.get("net_value")
    if net is not None:
        try:
            return int(net)
        except (TypeError, ValueError):
            pass
    return 0


class DividendsService:
    """Aggregate provento operations into a structured summary."""

    def summarise(
        self,
        operations: Iterable[dict[str, Any]],
        *,
        period_start: date,
        period_end: date,
        portfolio_value_cents: int | None = None,
    ) -> dict[str, Any]:
        """Build the dividend summary payload from ``operations``.

        Args:
            operations: Pre-filtered iterable of operation rows (dicts as
                returned by :class:`OperationRepository`). Rows with an
                ``operation_type`` outside :data:`PROVENT_TYPES` are skipped
                so callers can safely pass an unfiltered query result.
            period_start, period_end: Inclusive ISO window used to populate
                the ``period`` block and compute monthly averages.
            portfolio_value_cents: Current total portfolio value (sum of
                market values) used as the denominator for the DY estimate.
                ``None`` or non-positive disables the DY block.

        Returns:
            JSON-serialisable dict matching the documented contract.
        """
        if period_end < period_start:
            raise ValueError(
                "period_end must be on or after period_start "
                f"(got {period_start.isoformat()} → {period_end.isoformat()})"
            )

        by_asset: dict[str, _AssetBucket] = {}
        by_month_total: dict[str, int] = defaultdict(int)
        by_month_count: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = {f"{t}_cents": 0 for t in sorted(PROVENT_TYPES)}
        total_cents = 0
        events_count = 0

        for row in operations:
            op_type = str(row.get("operation_type", ""))
            if op_type not in PROVENT_TYPES:
                continue

            amount = _amount_cents(row)
            asset_code = str(row.get("asset_code", "")).strip()
            if not asset_code:
                continue

            op_date = str(row.get("operation_date", ""))
            try:
                d = _parse_date(op_date)
            except ValueError:
                # Defensive: an invalid date in storage shouldn't crash the tool.
                continue
            if d < period_start or d > period_end:
                continue

            bucket = by_asset.get(asset_code)
            if bucket is None:
                bucket = _AssetBucket(
                    asset_code=asset_code,
                    asset_name=row.get("asset_name"),
                )
                by_asset[asset_code] = bucket
            elif bucket.asset_name is None and row.get("asset_name"):
                bucket.asset_name = row.get("asset_name")

            bucket.total_cents += amount
            bucket.events.append(
                DividendEvent(
                    operation_date=d.isoformat(),
                    operation_type=op_type,
                    amount_cents=amount,
                )
            )

            month_key = d.strftime("%Y-%m")
            by_month_total[month_key] += amount
            by_month_count[month_key] += 1

            by_type[f"{op_type}_cents"] = by_type.get(f"{op_type}_cents", 0) + amount
            total_cents += amount
            events_count += 1

        months = max(1, _months_between(period_start, period_end))
        monthly_average = (
            int((Decimal(total_cents) / Decimal(months)).to_integral_value(rounding=ROUND_HALF_EVEN))
            if events_count
            else 0
        )

        by_asset_payload = []
        for asset in sorted(by_asset.values(), key=lambda a: (-a.total_cents, a.asset_code)):
            sorted_events = sorted(asset.events, key=lambda e: e.operation_date)
            by_asset_payload.append(
                {
                    "asset_code": asset.asset_code,
                    "asset_name": asset.asset_name,
                    "total_cents": asset.total_cents,
                    "events_count": len(sorted_events),
                    "events": [
                        {
                            "date": ev.operation_date,
                            "type": ev.operation_type,
                            "amount_cents": ev.amount_cents,
                        }
                        for ev in sorted_events
                    ],
                }
            )

        by_month_payload = [
            {
                "month": month,
                "total_cents": by_month_total[month],
                "events_count": by_month_count[month],
            }
            for month in sorted(by_month_total)
        ]

        payload: dict[str, Any] = {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "months": months,
            },
            "totals": {
                "total_received_cents": total_cents,
                "events_count": events_count,
                "monthly_average_cents": monthly_average,
            },
            "by_asset": by_asset_payload,
            "by_month": by_month_payload,
            "by_type": by_type,
        }

        if portfolio_value_cents is not None and portfolio_value_cents > 0:
            dy = (Decimal(total_cents) / Decimal(portfolio_value_cents)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            payload["portfolio_dy_estimate"] = {
                "value": float(dy),
                "method": (
                    f"received_{months}m / current_total_value"
                    if months != 12
                    else "received_12m / current_total_value"
                ),
                "note": (
                    "DY estimado: proventos recebidos no período dividido "
                    "pelo valor atual da carteira (não é DY oficial do emissor)."
                ),
                "portfolio_value_cents": portfolio_value_cents,
            }
        else:
            payload["portfolio_dy_estimate"] = None

        return payload


def _months_between(start: date, end: date) -> int:
    """Whole-month count between two inclusive dates (minimum 1)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day >= start.day:
        months += 1
    return max(1, months)


__all__ = ["DividendEvent", "DividendsService", "PROVENT_TYPES"]
