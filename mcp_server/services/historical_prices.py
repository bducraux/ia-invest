"""Historical price service — Yahoo Finance backfill + SQLite cache.

Fetches monthly closing prices from Yahoo Finance's v8 chart endpoint and
persists them into ``historical_prices``. A single HTTP call returns the
entire requested range, so backfilling a portfolio is just one request per
asset.

Closing prices for past dates are immutable, so the cache has no TTL — once
a date is stored it is never re-fetched. The service only hits Yahoo for
gaps in the requested coverage.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from storage.repository.historical_prices import HistoricalPricesRepository

LOG = logging.getLogger(__name__)

# Asset types that map to Brazilian B3-listed tickers (Yahoo uses .SA suffix).
_BR_ASSET_TYPES = {"stock", "fii", "etf", "bdr", "bond"}
# Asset types listed on US markets (no suffix).
_US_ASSET_TYPES = {"stock_us", "etf_us", "reit_us", "bdr_us"}
# Crypto uses ``BTC-USD`` style symbols on Yahoo.
_CRYPTO_ASSET_TYPES = {"crypto"}


@dataclass(frozen=True)
class HistoricalPriceFetchResult:
    asset_code: str
    rows_inserted: int
    coverage_start: date | None
    coverage_end: date | None
    source: str  # "cache_only" | "yahoo" | "no_data"


class HistoricalPriceService:
    """Backfill + lookup historical closing prices, cached in SQLite."""

    def __init__(
        self,
        repo: HistoricalPricesRepository,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._repo = repo
        self._timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_close_on_or_before(
        self,
        asset_code: str,
        asset_type: str,
        rate_date: date,
    ) -> tuple[int, str, str] | None:
        """Return ``(close_cents, currency, source)`` for the closest cached
        price at or before ``rate_date``. Triggers a single Yahoo backfill
        when nothing is cached for ``asset_code``.
        """
        cached = self._repo.get_latest_on_or_before(asset_code, rate_date)
        if cached is not None:
            _, cents, currency, source = cached
            return cents, currency, source

        # Nothing cached — backfill from a wide range and try again.
        # 5-year window covers most portfolios' active history in 1 request.
        start = date(rate_date.year - 5, 1, 1)
        end = max(date.today(), rate_date)
        self.backfill(asset_code, asset_type, start, end)

        cached = self._repo.get_latest_on_or_before(asset_code, rate_date)
        if cached is None:
            return None
        _, cents, currency, source = cached
        return cents, currency, source

    def backfill(
        self,
        asset_code: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> HistoricalPriceFetchResult:
        """Ensure monthly closing prices cover ``[start_date, end_date]``.

        Skips fetching when the cache already covers the requested range
        (within one calendar month). Otherwise pulls the entire range from
        Yahoo in a single HTTP call and persists it.
        """
        cov_start, cov_end, _ = self._repo.get_coverage(asset_code)
        if (
            cov_start is not None
            and cov_end is not None
            and cov_start <= start_date
            and cov_end >= end_date - timedelta(days=31)
        ):
            return HistoricalPriceFetchResult(
                asset_code=asset_code.upper(),
                rows_inserted=0,
                coverage_start=cov_start,
                coverage_end=cov_end,
                source="cache_only",
            )

        rows = self._fetch_yahoo_monthly(asset_code, asset_type, start_date, end_date)
        if not rows:
            return HistoricalPriceFetchResult(
                asset_code=asset_code.upper(),
                rows_inserted=0,
                coverage_start=cov_start,
                coverage_end=cov_end,
                source="no_data",
            )

        inserted = self._repo.upsert_many(rows)
        cov_start, cov_end, _ = self._repo.get_coverage(asset_code)
        return HistoricalPriceFetchResult(
            asset_code=asset_code.upper(),
            rows_inserted=inserted,
            coverage_start=cov_start,
            coverage_end=cov_end,
            source="yahoo",
        )

    # ------------------------------------------------------------------
    # Yahoo HTTP integration
    # ------------------------------------------------------------------

    def _fetch_yahoo_monthly(
        self,
        asset_code: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> list[tuple[str, date, int, str, str]]:
        symbol_candidates, currency = self._yahoo_symbol_candidates(asset_code, asset_type)
        if not symbol_candidates:
            return []

        period1 = int(datetime.combine(start_date, datetime.min.time(), tzinfo=UTC).timestamp())
        period2 = int(datetime.combine(end_date, datetime.min.time(), tzinfo=UTC).timestamp())

        for symbol in symbol_candidates:
            params = urlencode(
                {
                    "period1": period1,
                    "period2": period2,
                    "interval": "1mo",
                    "events": "history",
                }
            )
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
            payload = self._fetch_json(url)
            parsed = self._parse_yahoo_payload(payload)
            if parsed is None:
                continue
            timestamps, closes, payload_currency = parsed
            actual_currency = payload_currency or currency
            rows: list[tuple[str, date, int, str, str]] = []
            for ts, close in zip(timestamps, closes, strict=False):
                if close is None:
                    continue
                d = datetime.fromtimestamp(ts, tz=UTC).date()
                cents = int(round(float(close) * 100))
                rows.append((asset_code.upper(), d, cents, actual_currency, "yahoo"))
            if rows:
                return rows

        return []

    def _yahoo_symbol_candidates(
        self, asset_code: str, asset_type: str
    ) -> tuple[list[str], str]:
        """Return ``(candidates, default_currency)``."""
        code = asset_code.upper().strip()
        normalized_type = asset_type.lower() if asset_type else ""
        if normalized_type in _CRYPTO_ASSET_TYPES:
            # Cripto: try -USD then -BRL.
            return [f"{code}-USD", f"{code}-BRL"], "USD"
        if normalized_type in _US_ASSET_TYPES:
            return [code], "USD"
        if normalized_type in _BR_ASSET_TYPES or normalized_type == "":
            return [f"{code}.SA", code], "BRL"
        return [], "BRL"

    def _parse_yahoo_payload(
        self, payload: Any
    ) -> tuple[list[int], list[float | None], str | None] | None:
        if not isinstance(payload, dict):
            return None
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            return None
        results = chart.get("result")
        if not isinstance(results, list) or not results:
            return None
        first = results[0]
        if not isinstance(first, dict):
            return None
        timestamps = first.get("timestamp")
        indicators = first.get("indicators", {})
        quote = (indicators.get("quote") or [{}])[0] if isinstance(indicators, dict) else {}
        closes = quote.get("close") if isinstance(quote, dict) else None
        if not isinstance(timestamps, list) or not isinstance(closes, list):
            return None
        meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
        currency = meta.get("currency") if isinstance(meta, dict) else None
        if isinstance(currency, str):
            currency = currency.upper()
        return list(timestamps), list(closes), currency

    def _fetch_json(self, url: str) -> Any | None:
        req = Request(url, headers={"User-Agent": "ia-invest/0.1"})
        try:
            with urlopen(req, timeout=self._timeout_seconds) as response:  # noqa: S310
                data = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            LOG.debug("Yahoo historical fetch failed for %s: %s", url, exc)
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None


def backfill_assets(
    service: HistoricalPriceService,
    assets: Iterable[tuple[str, str]],
    start_date: date,
    end_date: date,
) -> list[HistoricalPriceFetchResult]:
    """Convenience helper: backfill many ``(asset_code, asset_type)`` pairs."""
    results: list[HistoricalPriceFetchResult] = []
    for asset_code, asset_type in assets:
        result = service.backfill(asset_code, asset_type, start_date, end_date)
        results.append(result)
    return results
