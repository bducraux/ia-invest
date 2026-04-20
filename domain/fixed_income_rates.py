"""Daily benchmark rate providers for fixed-income valuation.

A *daily rate* is the published per-day rate for a benchmark such as
CDI, expressed as a fraction (e.g. ``Decimal("0.00045123")`` for ~0.045%
per business day, equivalent to ~12.42% per year compounded over 252
business days).

Only CDI is supported in V1, but the interface accepts a ``benchmark``
name so future implementations (Selic, IPCA, etc.) can plug in without
breaking the contract.

The V1 MVP ships an in-memory provider only; real implementations
(BACEN/BCB time series, broker exports, etc.) should subclass
:class:`DailyRateProvider` and be wired up by the application layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from decimal import Decimal


def _to_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


class DailyRateProvider(ABC):
    """Abstract source of daily benchmark rates (e.g. CDI)."""

    @abstractmethod
    def get_daily_rates(
        self,
        start_date: date | str,
        end_date: date | str,
        benchmark: str = "CDI",
    ) -> dict[date, Decimal]:
        """Return a mapping ``{date: daily_rate_fraction}`` for the period.

        Implementations should:

        * Return rates **only for business days** (weekends/holidays
          omitted). The valuation service treats missing dates as
          non-business days and skips them.
        * Cover the inclusive range ``[start_date, end_date]``. If part
          of the range is unavailable, return what is available — the
          valuation service is responsible for detecting gaps and
          flagging the calculation as incomplete.
        * Use :class:`~decimal.Decimal` for rate values to preserve
          precision.
        """


class InMemoryCDIRateProvider(DailyRateProvider):
    """Test-friendly provider backed by a fixed dict.

    Useful for unit tests and as a fallback during local development
    when the real series is not yet wired up. Production use should
    replace this with an adapter to a real source.
    """

    def __init__(self, rates: dict[date | str, Decimal | str | float]) -> None:
        self._rates: dict[date, Decimal] = {}
        for raw_date, raw_rate in rates.items():
            self._rates[_to_date(raw_date)] = Decimal(str(raw_rate))

    def get_daily_rates(
        self,
        start_date: date | str,
        end_date: date | str,
        benchmark: str = "CDI",
    ) -> dict[date, Decimal]:
        if benchmark.upper() != "CDI":
            raise ValueError(f"InMemoryCDIRateProvider only serves CDI, got {benchmark!r}")
        start = _to_date(start_date)
        end = _to_date(end_date)
        return {d: r for d, r in self._rates.items() if start <= d <= end}


class FlatCDIRateProvider(DailyRateProvider):
    """Convenience provider that returns the same daily rate for every business day.

    Useful for examples and tests where the exact daily series is not
    important. Skips weekends (Mon=0..Sun=6 → 5,6 are weekend). This
    provider does **not** know about brazilian holidays; tests that
    need holidays should use :class:`InMemoryCDIRateProvider`.
    """

    def __init__(self, daily_rate: Decimal | str | float) -> None:
        self._rate = Decimal(str(daily_rate))

    def get_daily_rates(
        self,
        start_date: date | str,
        end_date: date | str,
        benchmark: str = "CDI",
    ) -> dict[date, Decimal]:
        if benchmark.upper() != "CDI":
            raise ValueError(f"FlatCDIRateProvider only serves CDI, got {benchmark!r}")
        start = _to_date(start_date)
        end = _to_date(end_date)
        out: dict[date, Decimal] = {}
        cursor = start
        one_day = timedelta(days=1)
        while cursor <= end:
            if cursor.weekday() < 5:    # Mon..Fri
                out[cursor] = self._rate
            cursor += one_day
        return out
