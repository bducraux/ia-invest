"""Market quote service with cache and external providers (Brapi + Binance)."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from storage.repository.quotes import QuoteRepository


class MarketQuoteService:
    def __init__(self, conn: Any, *, enabled: bool, ttl_seconds: int = 300, timeout_seconds: float = 2.0) -> None:
        self._cache = QuoteRepository(conn)
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        self._timeout_seconds = timeout_seconds

    def get_price_cents(self, asset_code: str, asset_type: str) -> int | None:
        code = asset_code.upper().strip()
        if not code:
            return None

        cached = self._cache.get_fresh(code, max_age_seconds=self._ttl_seconds)
        if cached is not None:
            return int(cached["price_cents"])

        if not self._enabled:
            return None

        quote = self._fetch_live_quote(code, asset_type)
        if quote is None:
            return None

        cents, source = quote
        self._cache.upsert(code, cents, source)
        return cents

    def _fetch_live_quote(self, code: str, asset_type: str) -> tuple[int, str] | None:
        normalized = asset_type.lower()
        if normalized in {"stock", "fii", "etf", "bdr", "bond"}:
            return self._fetch_brapi(code)
        if normalized == "crypto":
            return self._fetch_binance(code)
        return None

    def _fetch_brapi(self, code: str) -> tuple[int, str] | None:
        url = f"https://brapi.dev/api/quote/{code}"
        payload = self._fetch_json(url)
        if payload is None:
            return None

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return None

        first = results[0]
        if not isinstance(first, dict):
            return None

        raw_price = first.get("regularMarketPrice")
        if not isinstance(raw_price, (int, float)):
            return None
        return int(round(float(raw_price) * 100)), "brapi"

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
