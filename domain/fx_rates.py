"""Foreign exchange (FX) rate management for portfolio normalization.

Handles conversion of trading values to base currency (BRL) using:
- Direct pairs (USDTBRL, ETHBRL, BTCBRL)
- Indirect pairs via rate composition (e.g., ETHBRL = ETHUSDT * USDTBRL)
- Local cache of historical rates for reproducibility
"""

from __future__ import annotations


class FXRate:
    """Single FX rate for a currency pair at a specific date."""

    __slots__ = ("pair", "rate_date", "rate", "source", "method")

    def __init__(
        self,
        pair: str,
        rate_date: str,
        rate: float,
        source: str = "unknown",
        method: str = "direct",
    ) -> None:
        """Initialize FX rate.

        Args:
            pair: e.g., "USDTBRL", "ETHBRL"
            rate_date: ISO 8601 date (YYYY-MM-DD)
            rate: Exchange rate (units of quote per unit of base)
            source: Origin (e.g., "binance_klines", "manual", "composite")
            method: "direct" (from pair) or "composite" (calculated)
        """
        self.pair = pair.upper()
        self.rate_date = rate_date
        self.rate = float(rate)
        self.source = source
        self.method = method

    def __repr__(self) -> str:
        return f"FXRate({self.pair} {self.rate_date}: {self.rate} via {self.source})"


class FXRateCache:
    """In-memory cache of historical FX rates.

    Initially populated with manual rates or loaded from storage.
    Can be extended with rates fetched from Binance klines API.
    """

    def __init__(self) -> None:
        self._rates: dict[tuple[str, str], FXRate] = {}
        self._bootstrap_manual_rates()

    def _bootstrap_manual_rates(self) -> None:
        """Add well-known historical rates for testing and fallback.

        These are approximate reference rates; real implementation would
        fetch current rates from Binance klines API.
        """
        manual_rates = [
            # USDT to BRL
            ("USDTBRL", "2026-04-13", 5.0007),
            ("USDTBRL", "2026-03-20", 5.3128),
            ("USDTBRL", "2026-02-10", 4.997),
            ("USDTBRL", "2024-02-10", 4.997),
            ("USDTBRL", "2024-01-25", 5.043),
            ("USDTBRL", "2024-03-09", 5.045),
            ("USDTBRL", "2023-12-26", 4.854),
            ("USDTBRL", "2022-06-12", 5.121),
            ("USDTBRL", "2022-04-01", 4.75),
            ("USDTBRL", "2022-02-21", 5.125),
            # ETH to BRL (approximate)
            ("ETHBRL", "2025-11-14", 16474),
            ("ETHBRL", "2024-03-08", 19590),
            ("ETHBRL", "2022-06-13", 6000),
            ("ETHBRL", "2021-10-07", 20000),
            ("ETHBRL", "2021-02-22", 9500),
            # BTC to BRL (approximate)
            ("BTCBRL", "2024-01-23", 193100),
            ("BTCBRL", "2024-01-08", 164000),
            ("BTCBRL", "2023-11-14", 174530),
            ("BTCBRL", "2022-11-20", 88900),
            ("BTCBRL", "2022-11-08", 94200),
            ("BTCBRL", "2022-06-13", 119000),
            ("BTCBRL", "2021-07-20", 156382),
            ("BTCBRL", "2021-05-18", 227000),
            # BTC to USDT (for composite conversions)
            ("BTCUSDT", "2022-06-12", 26800),
            ("BTCUSDT", "2022-02-21", 40000),
            ("ETHUSDT", "2025-11-13", 3212.14),
            # BNB and LINK to approximate rates
            ("BNBUSDT", "2022-04-29", 400),
            ("LINKBRL", "2024-05-14", 68.9),
            ("LINKBRL", "2024-10-10", 90.8),
            ("LINKUSDT", "2024-04-11", 17.339),
            # BUSD ≈ USDT
            ("BUSDBRL", "2021-05-11", 5.26),
            ("BUSDUSDT", "2021-10-27", 1.0),
            # ADA rates
            ("ADABRL", "2021-11-24", 9),
            ("ADABRL", "2021-11-22", 10.051),
            ("ADABUSD", "2021-10-27", 1.918),
            # SHIB to BUSD
            ("SHIBBUSD", "2021-05-15", 0.000016),
            # MATIC rates
            ("MATICBRL", "2024-03-13", 6.119),
            ("MATICUSDT", "2024-03-09", 1.1307),
            # Default fallback rate (approx 5 BRL per USD)
            ("USDTBRL", "2020-01-01", 5.0),
        ]

        for pair, rate_date, rate in manual_rates:
            self.add_rate(pair, rate_date, rate, source="manual")

    def add_rate(
        self,
        pair: str,
        rate_date: str,
        rate: float,
        source: str = "unknown",
        method: str = "direct",
    ) -> None:
        """Add or update an FX rate."""
        key = (pair.upper(), rate_date)
        self._rates[key] = FXRate(pair, rate_date, rate, source, method)

    def get_rate(
        self, pair: str, rate_date: str, default: float | None = None
    ) -> float | None:
        """Retrieve exchange rate for a pair on a specific date.

        Tries exact date first, then falls back to the most recent rate before
        the requested date (for handling missing intermediate dates).

        Returns the rate if found, else default (None).
        """
        pair = pair.upper()
        key = (pair, rate_date)
        
        # Exact match
        if key in self._rates:
            return self._rates[key].rate
        
        # Fallback: find most recent rate before the requested date
        matching_dates = [
            date_str
            for (p, date_str) in self._rates.keys()
            if p == pair and date_str <= rate_date
        ]
        
        if matching_dates:
            closest_date = max(matching_dates)
            return self._rates[(pair, closest_date)].rate
        
        return default

    def get_rate_with_info(
        self, pair: str, rate_date: str
    ) -> tuple[float, str, str] | None:
        """Retrieve rate with source and method metadata.

        Returns: (rate, source, method) or None if not found.
        """
        key = (pair.upper(), rate_date)
        if key in self._rates:
            r = self._rates[key]
            return r.rate, r.source, r.method
        return None

    def __len__(self) -> int:
        return len(self._rates)

    def __repr__(self) -> str:
        return f"FXRateCache({len(self._rates)} rates)"


def normalize_to_brl(
    gross_value: float,
    quote_currency: str,
    rate_date: str,
    fx_cache: FXRateCache,
) -> tuple[float, str]:
    """Convert trading value to BRL using FX cache.

    Args:
        gross_value: Value in the quote currency (e.g., 1248.02955)
        quote_currency: Currency of gross_value (e.g., "BRL", "BTC", "USDT")
        rate_date: ISO date (YYYY-MM-DD) for rate lookup
        fx_cache: FX rate cache instance

    Returns:
        (value_in_brl, method_description)
        where method_description is "direct" or "composite" or "no_conversion"

    Raises:
        ValueError: If quote_currency is not BRL and rate cannot be found.
    """
    quote_currency = quote_currency.upper()

    # Already in BRL, no conversion needed
    if quote_currency == "BRL":
        return gross_value, "no_conversion"

    # Try direct pair (e.g., USDTBRL, ETHBRL)
    direct_pair = f"{quote_currency}BRL"
    rate = fx_cache.get_rate(direct_pair, rate_date)
    if rate is not None:
        return gross_value * rate, "direct"

    # If quote_currency is BTC, try BTCBRL
    if quote_currency == "BTC":
        rate = fx_cache.get_rate("BTCBRL", rate_date)
        if rate is not None:
            return gross_value * rate, "direct"

    # If quote_currency is BNB, try BNBBRL
    if quote_currency == "BNB":
        rate = fx_cache.get_rate("BNBBRL", rate_date)
        if rate is not None:
            return gross_value * rate, "direct"

    # Composite: try XXX -> USDT -> BRL
    usdt_pair = f"{quote_currency}USDT"
    usdt_rate = fx_cache.get_rate(usdt_pair, rate_date)
    brl_rate = fx_cache.get_rate("USDTBRL", rate_date)

    if usdt_rate is not None and brl_rate is not None:
        return gross_value * usdt_rate * brl_rate, "composite"

    # No rate found
    raise ValueError(
        f"Cannot convert {quote_currency} to BRL on {rate_date}: "
        f"pair not in cache. Tried {direct_pair} and composite via USDT."
    )
