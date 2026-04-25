"""Position valuation service — compute market value and unrealised P&L.

Pure domain service: no database, no network. Given a stored
:class:`~domain.models.Position` and an optional current quote in cents,
produces a :class:`ValuedPosition` with market value, unrealised P&L (cents
and percentage) and quote provenance.

All arithmetic uses :class:`~decimal.Decimal`; boundary rounding is
``ROUND_HALF_EVEN`` and outputs are integer cents to match the rest of the
codebase.

Negative quantities (resulting from historical-data gaps where sells appear
before the original buys) are **preserved**, never clamped — see
``WALLET_MODEL.md`` and the lessons captured in
``tests/test_bulletproof_lessons.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from domain.models import Position

#: Quantize unrealised P&L percentage to 4 decimals (e.g. 0.0824 = 8.24%).
_PCT_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class ValuedPosition:
    """A position enriched with current-quote valuation and provenance.

    All monetary fields are integer cents. ``current_price_cents`` and the
    derived market-value/P&L fields are ``None`` when no quote is available
    — the position itself is still returned so the caller can render it.
    """

    portfolio_id: str
    asset_code: str
    asset_type: str
    asset_name: str | None
    quantity: float
    avg_price_cents: int
    total_cost_cents: int

    current_price_cents: int | None
    current_value_cents: int | None
    unrealized_pnl_cents: int | None
    unrealized_pnl_pct: float | None

    quote_source: str | None
    quote_age_seconds: int | None
    quote_status: str | None
    quote_fetched_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_code": self.asset_code,
            "asset_type": self.asset_type,
            "asset_name": self.asset_name,
            # Quantity as string preserves precision for fractional cripto
            # holdings (e.g. ``0.00012345`` BTC) where float JSON encoding
            # may otherwise round. ``repr`` produces the shortest
            # round-trippable representation of a Python float.
            "quantity": repr(self.quantity),
            "avg_price_cents": self.avg_price_cents,
            "total_cost_cents": self.total_cost_cents,
            "current_price_cents": self.current_price_cents,
            "current_value_cents": self.current_value_cents,
            "unrealized_pnl_cents": self.unrealized_pnl_cents,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "quote_source": self.quote_source,
            "quote_age_seconds": self.quote_age_seconds,
            "quote_status": self.quote_status,
            "quote_fetched_at": self.quote_fetched_at,
        }


class PositionValuationService:
    """Compute market value and unrealised P&L for a position."""

    def value(
        self,
        position: Position,
        quote: dict[str, Any] | None,
    ) -> ValuedPosition:
        """Return a :class:`ValuedPosition` for ``position`` with ``quote``.

        ``quote`` is the dict shape returned by
        :class:`mcp_server.services.quotes.MarketQuoteService.resolve_price`
        or ``None`` when no quote is available.
        """
        price_cents = self._extract_price_cents(quote)
        source = self._extract_str(quote, "source")
        age = self._extract_int(quote, "age_seconds")
        status = self._extract_str(quote, "status")
        fetched_at = self._extract_str(quote, "fetched_at")

        if price_cents is None:
            return ValuedPosition(
                portfolio_id=position.portfolio_id,
                asset_code=position.asset_code,
                asset_type=position.asset_type,
                asset_name=position.asset_name,
                quantity=position.quantity,
                avg_price_cents=int(position.avg_price),
                total_cost_cents=int(position.total_cost),
                current_price_cents=None,
                current_value_cents=None,
                unrealized_pnl_cents=None,
                unrealized_pnl_pct=None,
                quote_source=source,
                quote_age_seconds=age,
                quote_status=status,
                quote_fetched_at=fetched_at,
            )

        # Use Decimal everywhere so 0.1 * 100 doesn't become 10.000...0001.
        qty = Decimal(str(position.quantity))
        price = Decimal(price_cents)
        market_value = (qty * price).to_integral_value(rounding=ROUND_HALF_EVEN)

        cost = Decimal(int(position.total_cost))
        # ``total_cost`` is stored as a positive integer (sum of buys).
        # Unrealised P&L = current market value - cost basis.
        pnl = market_value - cost
        pnl_pct = (
            (pnl / cost).quantize(_PCT_QUANT, rounding=ROUND_HALF_EVEN)
            if cost != 0
            else None
        )

        return ValuedPosition(
            portfolio_id=position.portfolio_id,
            asset_code=position.asset_code,
            asset_type=position.asset_type,
            asset_name=position.asset_name,
            quantity=position.quantity,
            avg_price_cents=int(position.avg_price),
            total_cost_cents=int(position.total_cost),
            current_price_cents=int(price_cents),
            current_value_cents=int(market_value),
            unrealized_pnl_cents=int(pnl),
            unrealized_pnl_pct=float(pnl_pct) if pnl_pct is not None else None,
            quote_source=source,
            quote_age_seconds=age,
            quote_status=status,
            quote_fetched_at=fetched_at,
        )

    @staticmethod
    def _extract_price_cents(quote: dict[str, Any] | None) -> int | None:
        if not quote:
            return None
        raw = quote.get("price_cents")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_str(quote: dict[str, Any] | None, key: str) -> str | None:
        if not quote:
            return None
        value = quote.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _extract_int(quote: dict[str, Any] | None, key: str) -> int | None:
        if not quote:
            return None
        value = quote.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["PositionValuationService", "ValuedPosition"]
