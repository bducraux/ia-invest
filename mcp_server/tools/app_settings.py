"""MCP tool: ``get_app_settings`` — global financial benchmark settings.

Returns the current CDI, SELIC and IPCA rates plus the dates of their last
sync. Daily benchmarks (CDI, SELIC) are stored as fractions per business day
in ``daily_benchmark_rates`` and are annualised using the standard Brazilian
252-business-day compounding convention. IPCA, when available, is stored as
an already-annualised reading in the ``app_settings`` k/v table.

Missing series are reported as ``null`` rather than failing the call: a
fresh database (or one before the first sync) is a normal state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from storage.repository.app_settings import (
    AppSettingsRepository,
    DailyBenchmarkSnapshot,
    IpcaSnapshot,
)
from storage.repository.db import Database

#: Brazilian convention: a year has 252 business days for CDI/SELIC compounding.
_BUSINESS_DAYS_PER_YEAR = 252

#: Quantize annual rates to 6 decimals (e.g. 0.117500) for stable JSON output.
_ANNUAL_QUANT = Decimal("0.000001")
#: Quantize daily rates to 8 decimals to preserve precision.
_DAILY_QUANT = Decimal("0.00000001")


def _annualise_daily(daily_rate: Decimal) -> Decimal:
    """Convert a daily rate (fraction) to an annual rate (fraction).

    Uses Brazilian 252-business-day convention: ``(1 + d) ** 252 - 1``.
    """
    one = Decimal(1)
    factor = one
    # ``Decimal ** int`` is exact for non-negative integer exponents.
    factor = (one + daily_rate) ** _BUSINESS_DAYS_PER_YEAR
    return (factor - one).quantize(_ANNUAL_QUANT, rounding=ROUND_HALF_EVEN)


def _format_daily(daily_rate: Decimal) -> float:
    return float(daily_rate.quantize(_DAILY_QUANT, rounding=ROUND_HALF_EVEN))


def _format_annual(annual_rate: Decimal) -> float:
    return float(annual_rate.quantize(_ANNUAL_QUANT, rounding=ROUND_HALF_EVEN))


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_payload(
    cdi: DailyBenchmarkSnapshot | None,
    selic: DailyBenchmarkSnapshot | None,
    ipca: IpcaSnapshot | None,
) -> dict[str, Any]:
    rates: dict[str, float | None] = {
        "cdi_annual": None,
        "selic_annual": None,
        "ipca_annual": None,
        "cdi_daily": None,
        "selic_daily": None,
    }
    last_sync: dict[str, str | None] = {
        "cdi": None,
        "selic": None,
        "ipca": None,
    }
    warnings: list[str] = []

    if cdi is not None:
        rates["cdi_annual"] = _format_annual(_annualise_daily(cdi.daily_rate))
        rates["cdi_daily"] = _format_daily(cdi.daily_rate)
        last_sync["cdi"] = cdi.rate_date.isoformat()
    else:
        warnings.append("cdi_unavailable")

    if selic is not None:
        rates["selic_annual"] = _format_annual(_annualise_daily(selic.daily_rate))
        rates["selic_daily"] = _format_daily(selic.daily_rate)
        last_sync["selic"] = selic.rate_date.isoformat()
    else:
        warnings.append("selic_unavailable")

    if ipca is not None:
        rates["ipca_annual"] = _format_annual(ipca.annual_rate)
        # Reference month is the meaningful "as of" date for IPCA. Surface
        # the first day of that month in ISO format for consumer parsing.
        reference = ipca.reference_month
        if len(reference) == 7:  # "YYYY-MM"
            reference = f"{reference}-01"
        last_sync["ipca"] = reference
    else:
        warnings.append("ipca_unavailable")

    payload: dict[str, Any] = {
        "rates": rates,
        "last_sync": last_sync,
        "as_of": _utc_now_iso(),
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def get_app_settings(db: Database) -> dict[str, Any]:
    """Return current global financial settings (CDI/SELIC/IPCA).

    Missing series are reported as ``null`` and listed under ``warnings``
    so downstream consumers can render a degraded UI without errors.
    """
    repo = AppSettingsRepository(db.connection)
    cdi = repo.get_latest_daily_benchmark("CDI")
    selic = repo.get_latest_daily_benchmark("SELIC")
    ipca = repo.get_ipca_snapshot()
    return _build_payload(cdi, selic, ipca)


__all__ = ["get_app_settings"]
