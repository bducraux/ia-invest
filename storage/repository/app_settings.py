"""Repository for the ``app_settings`` key/value table and benchmark rate lookups.

The ``app_settings`` table is a simple key/value store used for global
application settings (e.g. an externally-provided IPCA reading that is not
fetched from BACEN by the daily benchmark sync).

For the daily benchmark series (CDI, SELIC) the latest stored daily rate is
read from ``daily_benchmark_rates``. Daily rates there are stored as a
``Decimal`` *fraction* (e.g. ``0.000441`` for 0.0441%/business day) — see
``mcp_server/services/benchmark_sync.py``.

This repository never imposes business rules: it only loads the raw values.
Annualisation and shaping for the API layer happens in the consumer
(``mcp_server.tools.app_settings``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class DailyBenchmarkSnapshot:
    """Latest known daily rate for a benchmark series."""

    benchmark: str
    rate_date: date
    daily_rate: Decimal


@dataclass(frozen=True)
class IpcaSnapshot:
    """Most recent IPCA monthly reading.

    ``annual_rate`` is stored as a fraction (e.g. ``0.0451`` for 4.51%/year).
    """

    reference_month: str   # ISO YYYY-MM
    annual_rate: Decimal
    updated_at: str | None = None


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


class AppSettingsRepository:
    """Read/write helper for the ``app_settings`` k/v table and rate lookups.

    Only read methods are exposed today; writes are owned by the sync
    services and are intentionally not surfaced here.
    """

    # Setting keys used for IPCA (the daily benchmark sync covers CDI/SELIC
    # but not the monthly IPCA series).
    IPCA_ANNUAL_RATE_KEY = "ipca_annual_rate"
    IPCA_REFERENCE_MONTH_KEY = "ipca_reference_month"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Generic key/value access
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def get_with_timestamp(self, key: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "SELECT value, updated_at FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"]), str(row["updated_at"])

    # ------------------------------------------------------------------
    # Benchmark snapshots (CDI/SELIC are stored in daily_benchmark_rates)
    # ------------------------------------------------------------------

    def get_latest_daily_benchmark(self, benchmark: str) -> DailyBenchmarkSnapshot | None:
        bench = benchmark.upper()
        row = self._conn.execute(
            """
            SELECT rate_date, rate
            FROM daily_benchmark_rates
            WHERE benchmark = ?
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            (bench,),
        ).fetchone()
        if row is None:
            return None
        return DailyBenchmarkSnapshot(
            benchmark=bench,
            rate_date=_parse_iso_date(str(row["rate_date"])),
            daily_rate=Decimal(str(row["rate"])),
        )

    # ------------------------------------------------------------------
    # IPCA (monthly) — stored as plain settings k/v
    # ------------------------------------------------------------------

    def get_ipca_snapshot(self) -> IpcaSnapshot | None:
        rate = self.get_with_timestamp(self.IPCA_ANNUAL_RATE_KEY)
        if rate is None:
            return None
        rate_value, updated_at = rate
        try:
            annual = Decimal(rate_value)
        except (ArithmeticError, ValueError):
            return None
        ref_pair = self.get_with_timestamp(self.IPCA_REFERENCE_MONTH_KEY)
        reference = ref_pair[0] if ref_pair is not None else updated_at[:7]
        return IpcaSnapshot(
            reference_month=reference,
            annual_rate=annual,
            updated_at=updated_at,
        )


__all__ = [
    "AppSettingsRepository",
    "DailyBenchmarkSnapshot",
    "IpcaSnapshot",
]
