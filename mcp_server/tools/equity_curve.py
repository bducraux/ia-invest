"""MCP tool: ``get_portfolio_equity_curve`` — monthly patrimônio histórico.

Returns one point per month with the consolidated market value across all
asset classes (renda variável, internacional, cripto, renda fixa,
previdência), plus per-class breakdown, monthly net contributions and
dividends received.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
from typing import Any

from domain.monthly_equity_service import (
    build_default_service,
    equity_curve_to_payload,
)
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository

_DEFAULT_PERIOD_MONTHS = 24


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_month(value: str | None, *, fallback: date) -> str:
    if value is None:
        return f"{fallback.year:04d}-{fallback.month:02d}"
    if len(value) != 7 or value[4] != "-":
        raise ValueError(f"Invalid month '{value}': expected YYYY-MM")
    int(value[:4])
    int(value[5:])
    return value


def _months_back(today: date, months: int) -> date:
    y = today.year
    m = today.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def get_portfolio_equity_curve(
    db: Database,
    portfolio_id: str | None = None,
    *,
    from_month: str | None = None,
    to_month: str | None = None,
    period_months: int = _DEFAULT_PERIOD_MONTHS,
) -> dict[str, Any]:
    """Return the monthly equity-curve payload.

    Args:
        db: Open database.
        portfolio_id: Restrict to a single portfolio. ``None`` aggregates
            across all known portfolios (consolidated).
        from_month: ``YYYY-MM`` lower bound (inclusive). Defaults to
            ``period_months`` before today.
        to_month: ``YYYY-MM`` upper bound (inclusive). Defaults to
            current month.
        period_months: Window size used when ``from_month`` is not provided.
    """
    portfolios_repo = PortfolioRepository(db.connection)

    if portfolio_id is None:
        portfolio_ids = [p.id for p in portfolios_repo.list_all()]
    else:
        if portfolios_repo.get(portfolio_id) is None:
            return {"error": f"Portfolio '{portfolio_id}' not found."}
        portfolio_ids = [portfolio_id]

    if not portfolio_ids:
        return {
            "portfolio_ids": [],
            "from_month": None,
            "to_month": None,
            "series": [],
            "generated_at": _utc_now_iso(),
        }

    # Local date — matches the rest of the API (e.g. PortfolioSummaryService
    # uses date.today() for month windows). Using UTC here would tip the
    # current point into next month after ~21:00 BRT, leaving the chart out
    # of sync with the "Total investido" KPI.
    today = date.today()
    end_default = date(today.year, today.month, 1)
    start_default = _months_back(end_default, period_months)
    try:
        from_month_norm = _normalize_month(
            from_month, fallback=start_default
        )
        to_month_norm = _normalize_month(to_month, fallback=end_default)
    except ValueError as exc:
        return {"error": str(exc)}

    if from_month_norm > to_month_norm:
        return {"error": f"from_month '{from_month_norm}' is after to_month '{to_month_norm}'"}

    service = build_default_service(db)
    points = service.compute(portfolio_ids, from_month_norm, to_month_norm)

    payload = equity_curve_to_payload(portfolio_ids, points)
    payload["generated_at"] = _utc_now_iso()
    return payload


def _last_day_of_month(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


__all__ = ["get_portfolio_equity_curve"]
