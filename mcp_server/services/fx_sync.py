"""Sync historical FX rates (BACEN PTAX) into the SQLite cache.

Wrapper around :class:`mcp_server.services.fx_rates.FxRateService` that
exposes a synchronous, cache-aware sync API mirroring
``BACENBenchmarkSyncService`` so the HTTP layer and CLI script can share
the same logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from mcp_server.services.fx_rates import SUPPORTED_PAIRS, FxRateService
from storage.repository.fx_rates import FxRatesRepository

_logger = logging.getLogger(__name__)

#: Earliest date used when bootstrapping an empty cache.
DEFAULT_BOOTSTRAP_START: date = date(2018, 1, 1)


class FxSyncError(RuntimeError):
    """Raised when a FX sync attempt fails for a non-recoverable reason."""


@dataclass(frozen=True)
class FxSyncResult:
    pair: str
    rows_inserted: int
    coverage_start: date | None
    coverage_end: date | None
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "pair": self.pair,
            "rows_inserted": self.rows_inserted,
            "coverage_start": self.coverage_start.isoformat() if self.coverage_start else None,
            "coverage_end": self.coverage_end.isoformat() if self.coverage_end else None,
            "source": self.source,
        }


class FxSyncService:
    """Fetch daily FX rates from BACEN PTAX and cache them in SQLite."""

    def __init__(
        self,
        repo: FxRatesRepository,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._repo = repo
        self._service = FxRateService(repo, timeout_seconds=timeout_seconds)

    def sync(
        self,
        pair: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        full_refresh: bool = False,
    ) -> FxSyncResult:
        pair_u = pair.upper()
        if pair_u not in SUPPORTED_PAIRS:
            raise FxSyncError(
                f"Unsupported pair '{pair}'. Supported: {', '.join(SUPPORTED_PAIRS)}"
            )

        end = end_date or date.today()

        if start_date is None:
            if full_refresh:
                start = DEFAULT_BOOTSTRAP_START
            else:
                _, current_end, count = self._repo.get_coverage(pair_u)
                if count == 0 or current_end is None:
                    start = DEFAULT_BOOTSTRAP_START
                else:
                    start = current_end + timedelta(days=1)
        else:
            start = start_date

        if start > end:
            min_d, max_d, _count = self._repo.get_coverage(pair_u)
            return FxSyncResult(
                pair=pair_u,
                rows_inserted=0,
                coverage_start=min_d,
                coverage_end=max_d,
                source="bacen_ptax",
            )

        try:
            rows = self._service._fetch_bacen(pair_u, start, end)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            raise FxSyncError(
                f"Failed to fetch PTAX rates from BACEN: {exc}"
            ) from exc

        inserted = self._repo.upsert_many(pair_u, rows, source="bacen_ptax")
        min_d, max_d, _count = self._repo.get_coverage(pair_u)
        return FxSyncResult(
            pair=pair_u,
            rows_inserted=inserted,
            coverage_start=min_d,
            coverage_end=max_d,
            source="bacen_ptax",
        )
