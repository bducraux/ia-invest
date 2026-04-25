"""Market quote service with cache and external providers (Yahoo Finance + Google Finance + Binance)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from storage.repository.quotes import QuoteRepository


class MarketQuoteService:
    def __init__(
        self,
        conn: Any,
        *,
        enabled: bool,
        ttl_seconds: int = 300,
        timeout_seconds: float = 2.0,
        fx_service: Any | None = None,
    ) -> None:
        self._cache = QuoteRepository(conn)
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._fx_service = fx_service

    def get_price_cents(self, asset_code: str, asset_type: str) -> int | None:
        resolved = self.resolve_price(asset_code, asset_type)
        if resolved is None:
            return None
        return resolved["price_cents"]

    def resolve_price(
        self,
        asset_code: str,
        asset_type: str,
        *,
        fallback_price_cents: int | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        code = asset_code.upper().strip()
        if not code:
            return None

        if not force_refresh:
            cached = self._cache.get_fresh(code, max_age_seconds=self._ttl_seconds)
            if cached is not None:
                return {
                    "price_cents": int(cached["price_cents"]),
                    "source": str(cached["source"]),
                    "status": "cache_fresh",
                    "fetched_at": str(cached["fetched_at"]),
                    "age_seconds": int(cached["age_seconds"]) if cached.get("age_seconds") is not None else 0,
                }

        if not self._enabled:
            stale = self._cache.get_latest(code)
            if stale is not None:
                return {
                    "price_cents": int(stale["price_cents"]),
                    "source": str(stale["source"]),
                    "status": "cache_stale",
                    "fetched_at": str(stale["fetched_at"]),
                    "age_seconds": int(stale["age_seconds"]) if stale.get("age_seconds") is not None else None,
                }
            if fallback_price_cents is None:
                return None
            return {
                "price_cents": int(fallback_price_cents),
                "source": "avg_price",
                "status": "avg_fallback",
                "fetched_at": None,
                "age_seconds": None,
            }

        quote = self._fetch_live_quote(code, asset_type)
        if quote is not None:
            cents, source = quote
            self._cache.upsert(code, cents, source)
            return {
                "price_cents": int(cents),
                "source": source,
                "status": "live",
                "fetched_at": None,
                "age_seconds": 0,
            }

        stale = self._cache.get_latest(code)
        if stale is not None:
            return {
                "price_cents": int(stale["price_cents"]),
                "source": str(stale["source"]),
                "status": "cache_stale",
                "fetched_at": str(stale["fetched_at"]),
                "age_seconds": int(stale["age_seconds"]) if stale.get("age_seconds") is not None else None,
            }

        if fallback_price_cents is None:
            return None

        return {
            "price_cents": int(fallback_price_cents),
            "source": "avg_price",
            "status": "avg_fallback",
            "fetched_at": None,
            "age_seconds": None,
        }

    def _fetch_live_quote(self, code: str, asset_type: str) -> tuple[int, str] | None:
        normalized = asset_type.lower()
        if normalized in {"stock", "fii", "etf", "bdr", "bond"}:
            yahoo = self._fetch_yahoo(code)
            if yahoo is not None:
                return yahoo
            return self._fetch_google(code)
        if normalized in {"stock_us", "etf_us", "reit_us", "bdr_us"}:
            return self._fetch_us_ticker(code)
        if normalized == "crypto":
            return self._fetch_binance(code)
        return None

    def _fetch_us_ticker(self, code: str) -> tuple[int, str] | None:
        """Fetch a US ticker price (USD) and convert to BRL cents via FxRateService."""
        usd_price = self._fetch_yahoo_us_price(code)
        if usd_price is None:
            return None
        if self._fx_service is None:
            return None
        resolved = self._fx_service.get_current_rate("USDBRL")
        if resolved is None:
            return None
        rate = Decimal(str(resolved.rate))
        cents = int((Decimal(str(usd_price)) * rate * Decimal(100)).to_integral_value())
        return cents, f"yahoo_us+{resolved.source}"

    def _fetch_yahoo_us_price(self, code: str) -> float | None:
        """Fetch USD price for a US-listed ticker (no .SA suffix)."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}?interval=1d&range=5d"
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
        return float(raw_price)

    def _fetch_binance(self, code: str) -> tuple[int, str] | None:
        symbol_aliases = {
            "RENDER": "RNDR",
        }
        base_code = symbol_aliases.get(code, code)

        direct_brl = self._fetch_binance_symbol_price(f"{base_code}BRL")
        if direct_brl is not None:
            return int(round(direct_brl * 100)), "binance"

        usdt_price = self._fetch_binance_symbol_price(f"{base_code}USDT")
        usdt_brl = self._fetch_binance_symbol_price("USDTBRL")
        if usdt_price is not None and usdt_brl is not None:
            return int(round(usdt_price * usdt_brl * 100)), "binance"

        return None

    def _fetch_binance_symbol_price(self, symbol: str) -> float | None:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        payload = self._fetch_json(url)
        if payload is None:
            return None

        raw_price = payload.get("price")
        if raw_price is None:
            return None

        try:
            return float(raw_price)
        except (TypeError, ValueError):
            return None

    def _fetch_yahoo(self, code: str) -> tuple[int, str] | None:
        # Yahoo symbols for Brazilian assets commonly use the .SA suffix.
        # v8 chart endpoint is more reliable here than v7 quote endpoint.
        candidates = [f"{code}.SA", code]
        for symbol in candidates:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            payload = self._fetch_json(url)
            if payload is None:
                continue

            chart = payload.get("chart")
            if not isinstance(chart, dict):
                continue

            results = chart.get("result")
            if not isinstance(results, list) or not results:
                continue

            first = results[0]
            if not isinstance(first, dict):
                continue

            meta = first.get("meta")
            if not isinstance(meta, dict):
                continue

            raw_price = meta.get("regularMarketPrice")
            if not isinstance(raw_price, (int, float)):
                continue

            return int(round(float(raw_price) * 100)), "yahoo"

        return None

    def _fetch_google(self, code: str) -> tuple[int, str] | None:
        # Google Finance HTML parser for Brazilian assets.
        # Falls back if Yahoo fails, extracted via data-last-price attribute.
        url = f"https://www.google.com/finance/quote/{code}:BVMF"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urlopen(req, timeout=self._timeout_seconds) as response:  # noqa: S310
                html = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError):
            return None

        # Try to extract price from data-last-price attribute
        match = re.search(r'data-last-price="([\d.]+)"', html)
        if match:
            try:
                price_str = match.group(1)
                price_float = float(price_str)
                return int(round(price_float * 100)), "google"
            except (ValueError, IndexError):
                pass

        # Fallback: try to find BRL text pattern
        match = re.search(r'([\d.,]+)\s*R\$', html)
        if match:
            try:
                price_str = match.group(1).replace(".", "").replace(",", ".")
                price_float = float(price_str)
                return int(round(price_float * 100)), "google"
            except (ValueError, IndexError):
                pass

        return None

    def _fetch_json(self, url: str) -> dict[str, Any] | None:
        req = Request(url, headers={"User-Agent": "ia-invest/0.1"})
        try:
            with urlopen(req, timeout=self._timeout_seconds) as response:  # noqa: S310
                data = response.read()
        except (HTTPError, URLError, TimeoutError, OSError):
            return None

        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        if not isinstance(parsed, dict):
            return None
        return parsed
