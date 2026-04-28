"""Sync historical daily benchmark rates from BACEN SGS into SQLite.

Endpoint:
    https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados
    ?formato=json&dataInicial=DD/MM/YYYY&dataFinal=DD/MM/YYYY

Response shape:
    [{"data": "02/01/2024", "valor": "0.043739"}, ...]

``valor`` is **percent per business day** (0.043739 % ≈ ~0.000437 fraction).
Weekends and bank holidays are simply absent — that is the source of truth
we rely on to avoid maintaining a parallel holiday calendar.

Series codes (BACEN SGS):

* 12  — CDI diário (recommended for renda fixa)
* 11  — Selic over diária
* 433 — IPCA mensal (different shape; not implemented yet)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from storage.repository.benchmark_rates import BenchmarkRatesRepository

_logger = logging.getLogger(__name__)

#: BACEN SGS series codes (only daily-rate series currently supported).
_SERIES_MAP: dict[str, int] = {
    "CDI": 12,
    "SELIC": 11,
}

#: Default earliest date used when bootstrapping an empty cache. Covers any
#: realistic position lifetime in this codebase (oldest C6 application is
#: 2023-05-10) without ballooning the table size.
DEFAULT_BOOTSTRAP_START: date = date(2018, 1, 1)

_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"


class BenchmarkSyncError(RuntimeError):
    """Raised when a sync attempt fails for a non-recoverable reason."""


@dataclass(frozen=True)
class SyncResult:
    benchmark: str
    rows_inserted: int
    coverage_start: date | None
    coverage_end: date | None
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark": self.benchmark,
            "rows_inserted": self.rows_inserted,
            "coverage_start": self.coverage_start.isoformat() if self.coverage_start else None,
            "coverage_end": self.coverage_end.isoformat() if self.coverage_end else None,
            "source": self.source,
        }


class BACENBenchmarkSyncService:
    """Fetch daily benchmark rates from BACEN SGS and cache them in SQLite."""

    def __init__(
        self,
        repo: BenchmarkRatesRepository,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        self._repo = repo
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync(
        self,
        benchmark: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        full_refresh: bool = False,
    ) -> SyncResult:
        """Sync ``[start_date, end_date]`` for ``benchmark`` into SQLite.

        Defaults:

        * ``end_date`` → today (the BACEN endpoint silently truncates to
          the latest available business day).
        * ``start_date`` → if ``full_refresh`` or the cache is empty,
          :data:`DEFAULT_BOOTSTRAP_START`. Otherwise an incremental
          delta starting one day after the current ``coverage_end``.
        """
        bench = benchmark.upper()
        if bench not in _SERIES_MAP:
            raise BenchmarkSyncError(f"Unsupported benchmark: {benchmark!r}")

        today = date.today()
        if end_date is None:
            end_date = today
        if start_date is None:
            if full_refresh:
                start_date = DEFAULT_BOOTSTRAP_START
            else:
                _, current_end, count = self._repo.get_coverage(bench)
                if count == 0 or current_end is None:
                    start_date = DEFAULT_BOOTSTRAP_START
                else:
                    start_date = current_end + timedelta(days=1)

        if start_date > end_date:
            # Already up-to-date — nothing to fetch.
            min_d, max_d, _ = self._repo.get_coverage(bench)
            return SyncResult(
                benchmark=bench,
                rows_inserted=0,
                coverage_start=min_d,
                coverage_end=max_d,
                source="up_to_date",
            )

        rows = self._fetch(bench, start_date, end_date)
        inserted = self._repo.upsert_many(bench, rows)
        min_d, max_d, _ = self._repo.get_coverage(bench)
        return SyncResult(
            benchmark=bench,
            rows_inserted=inserted,
            coverage_start=min_d,
            coverage_end=max_d,
            source="bacen",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch(
        self,
        benchmark: str,
        start: date,
        end: date,
    ) -> list[tuple[date, Decimal]]:
        code = _SERIES_MAP[benchmark]
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        url = f"{_BASE_URL.format(code=code)}?{urlencode(params)}"
        payload = self._fetch_json(url)

        # BACEN responds 404 when the requested range has no business-day
        # data (e.g. today before publication, weekends, holidays). The
        # ``_fetch_json`` helper translates that into an empty list so we
        # treat it the same as "no new rows" instead of an error.
        if payload is None:
            return []

        if not isinstance(payload, list):
            raise BenchmarkSyncError(
                f"Unexpected BACEN response shape for {benchmark}: not a list"
            )

        out: list[tuple[date, Decimal]] = []
        for entry in payload:
            try:
                d = datetime.strptime(entry["data"], "%d/%m/%Y").date()
                # ``valor`` is percent per business day → convert to fraction.
                rate = Decimal(str(entry["valor"])) / Decimal(100)
            except (KeyError, ValueError, TypeError) as exc:
                raise BenchmarkSyncError(
                    f"Malformed BACEN row {entry!r}: {exc}"
                ) from exc
            out.append((d, rate))
        return out

    def _fetch_json(self, url: str) -> object:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                req = Request(url, headers={"User-Agent": "ia-invest/1.0"})
                with urlopen(req, timeout=self._timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                return json.loads(body)
            except HTTPError as exc:
                # 404 is BACEN's way of saying "no data in this range".
                # Common when the requested window only covers today (before
                # publication), weekends or holidays. Don't warn, don't retry.
                if exc.code == 404:
                    _logger.debug("bacen_no_data url=%s", url)
                    return None
                last_exc = exc
                _logger.warning(
                    "bacen_fetch_failed attempt=%d url=%s err=%s",
                    attempt + 1,
                    url,
                    exc,
                )
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_exc = exc
                _logger.warning(
                    "bacen_fetch_failed attempt=%d url=%s err=%s",
                    attempt + 1,
                    url,
                    exc,
                )
        raise BenchmarkSyncError(
            f"Could not fetch BACEN series after {self._max_retries + 1} attempt(s): {last_exc}"
        ) from last_exc
