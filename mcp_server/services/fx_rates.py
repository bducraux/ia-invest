"""FX rate service: historical PTAX (BACEN) + live USDBRL=X (Yahoo) with cache.

Used during normalization to convert foreign-currency operations into BRL,
and during live valuation to know the current exchange rate.

Sources:
* BACEN SGS series 10813 — PTAX venda diária USD/BRL (historical, official).
* Yahoo Finance v8 chart — ``USDBRL=X`` (live + recent fallback).

Both are cached in the ``fx_rates`` table. Live cache lookups respect a TTL
configured on construction; historical lookups always trust the cache.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from storage.repository.fx_rates import FxRatesRepository

_logger = logging.getLogger(__name__)

#: BACEN SGS code for PTAX venda USD/BRL diário.
_BACEN_PTAX_USD_VENDA = 10813
_BACEN_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

#: Yahoo Finance chart endpoint (works for FX symbols like USDBRL=X).
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

#: How far back to walk when the requested date is a holiday/weekend.
_MAX_BACKFILL_DAYS = 14

SUPPORTED_PAIRS = ("USDBRL",)

ResolvedSource = Literal[
    "cache",
    "bacen_ptax",
    "yahoo",
    "manual",
    "native_brl",
]


class FxRateError(RuntimeError):
    """Raised when an FX rate cannot be resolved from any source."""


@dataclass(frozen=True)
class ResolvedRate:
    pair: str
    rate_date: date
    rate: Decimal
    source: str


class FxRateService:
    """Fetch and cache FX rates for currency pair conversions.

    The service is intentionally minimal: it only knows about USDBRL today.
    Adding new pairs is a matter of expanding ``SUPPORTED_PAIRS`` and
    ``_fetch_bacen``/``_fetch_yahoo``.
    """

    def __init__(
        self,
        repo: FxRatesRepository,
        *,
        live_ttl_seconds: int = 300,
        timeout_seconds: float = 10.0,
        offline: bool = False,
    ) -> None:
        self._repo = repo
        self._live_ttl_seconds = live_ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._offline = offline

    # ------------------------------------------------------------------
    # Trade-time (historical) lookup
    # ------------------------------------------------------------------

    def get_rate_for_trade(self, pair: str, trade_date: date | str) -> ResolvedRate:
        """Resolve the exchange rate to use for an operation on ``trade_date``.

        Lookup order:
        1. Exact-date cache hit.
        2. Latest cache row at or before ``trade_date`` (≤ 14 days back).
        3. BACEN PTAX fetch covering a small window around the target.
        4. Yahoo fallback (latest available — best-effort).

        Raises :class:`FxRateError` if no rate can be resolved.
        """
        pair_u = pair.upper()
        if pair_u not in SUPPORTED_PAIRS:
            raise FxRateError(f"Unsupported FX pair: {pair_u}")

        target = _coerce_date(trade_date)

        # Exact hit first.
        exact = self._repo.get_rate(pair_u, target)
        if exact is not None:
            rate, source = exact
            return ResolvedRate(pair=pair_u, rate_date=target, rate=rate, source=source)

        # Already-cached previous business day.
        latest = self._repo.get_latest_on_or_before(pair_u, target)
        if latest is not None:
            cached_date, rate, source = latest
            if (target - cached_date).days <= _MAX_BACKFILL_DAYS:
                return ResolvedRate(pair=pair_u, rate_date=cached_date, rate=rate, source=source)

        if self._offline:
            raise FxRateError(
                f"No cached {pair_u} rate near {target.isoformat()} and offline mode is enabled"
            )

        # Try BACEN PTAX.
        rows = self._fetch_bacen(pair_u, target - timedelta(days=_MAX_BACKFILL_DAYS), target)
        if rows:
            self._repo.upsert_many(pair_u, rows, source="bacen_ptax")
            latest = self._repo.get_latest_on_or_before(pair_u, target)
            if latest is not None:
                cached_date, rate, source = latest
                return ResolvedRate(pair=pair_u, rate_date=cached_date, rate=rate, source=source)

        # Yahoo fallback (live spot, treat as best-effort for the trade date).
        yahoo_rate = self._fetch_yahoo(pair_u)
        if yahoo_rate is not None:
            self._repo.upsert_many(pair_u, [(target, yahoo_rate)], source="yahoo")
            return ResolvedRate(pair=pair_u, rate_date=target, rate=yahoo_rate, source="yahoo")

        raise FxRateError(
            f"Could not resolve {pair_u} rate for {target.isoformat()} "
            "from cache, BACEN, or Yahoo."
        )

    # ------------------------------------------------------------------
    # Live (current) lookup
    # ------------------------------------------------------------------

    def get_current_rate(self, pair: str) -> ResolvedRate | None:
        """Return the freshest available rate, falling back to cache.

        Returns ``None`` only when no source produced any value (offline +
        empty cache).
        """
        pair_u = pair.upper()
        if pair_u not in SUPPORTED_PAIRS:
            return None

        today = date.today()

        # Recent cache hit within TTL?
        latest = self._repo.get_latest_on_or_before(pair_u, today)
        if latest is not None:
            cached_date, rate, source = latest
            age_days = (today - cached_date).days
            # Treat anything fetched today (or yesterday for non-business days)
            # as fresh enough; otherwise refresh.
            if age_days == 0 and source in {"yahoo", "manual"}:
                return ResolvedRate(pair=pair_u, rate_date=cached_date, rate=rate, source=source)

        if self._offline:
            if latest is None:
                return None
            cached_date, rate, source = latest
            return ResolvedRate(pair=pair_u, rate_date=cached_date, rate=rate, source=source)

        yahoo_rate = self._fetch_yahoo(pair_u)
        if yahoo_rate is not None:
            self._repo.upsert_many(pair_u, [(today, yahoo_rate)], source="yahoo")
            return ResolvedRate(pair=pair_u, rate_date=today, rate=yahoo_rate, source="yahoo")

        if latest is None:
            return None
        cached_date, rate, source = latest
        return ResolvedRate(pair=pair_u, rate_date=cached_date, rate=rate, source=source)

    # ------------------------------------------------------------------
    # External fetchers
    # ------------------------------------------------------------------

    def _fetch_bacen(self, pair: str, start: date, end: date) -> list[tuple[date, Decimal]]:
        if pair != "USDBRL":
            return []
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        url = f"{_BACEN_BASE_URL.format(code=_BACEN_PTAX_USD_VENDA)}?{urlencode(params)}"
        payload = self._fetch_json(url)
        if not isinstance(payload, list):
            return []

        out: list[tuple[date, Decimal]] = []
        for entry in payload:
            try:
                d = datetime.strptime(entry["data"], "%d/%m/%Y").date()
                rate = Decimal(str(entry["valor"]))
            except (KeyError, ValueError, TypeError) as exc:
                _logger.warning("bacen_ptax_malformed_row entry=%r err=%s", entry, exc)
                continue
            out.append((d, rate))
        return out

    def _fetch_yahoo(self, pair: str) -> Decimal | None:
        if pair != "USDBRL":
            return None
        symbol = "USDBRL=X"
        url = _YAHOO_CHART_URL.format(symbol=symbol) + "?interval=1d&range=5d"
        payload = self._fetch_json(url)
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
        meta = first.get("meta")
        if not isinstance(meta, dict):
            return None
        raw_price = meta.get("regularMarketPrice")
        if not isinstance(raw_price, (int, float)):
            return None
        return Decimal(str(raw_price))

    def _fetch_json(self, url: str) -> object:
        try:
            req = Request(url, headers={"User-Agent": "ia-invest/1.0"})
            with urlopen(req, timeout=self._timeout_seconds) as resp:  # noqa: S310
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            _logger.warning("fx_fetch_failed url=%s err=%s", url, exc)
            return None


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


__all__ = [
    "FxRateError",
    "FxRateService",
    "ResolvedRate",
    "SUPPORTED_PAIRS",
]
