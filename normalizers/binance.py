"""Binance-specific operation normalizer.

Extends the base normalizer with Binance-specific logic:
- FX conversion to BRL using rate cache
- Deterministic external_id generation from trade data
- Fee currency handling (fees may be in a different currency than base asset)
"""

from __future__ import annotations

import hashlib
from typing import Any

from domain.fx_rates import FXRateCache, normalize_to_brl
from domain.models import Operation
from normalizers.validator import (
    normalise_asset_code,
    normalise_operation_type,
    parse_date,
)


class BinanceOperationNormalizer:
    """Normalizes Binance trade records to Operation domain objects."""

    def __init__(self, fx_cache: FXRateCache) -> None:
        self.fx_cache = fx_cache

    def normalize(self, record: dict[str, Any], portfolio_id: str = "default") -> Operation:
        """Convert a Binance trade record to a normalized Operation.

        Args:
            record: Raw record from BinanceCsvExtractor.extract()
            portfolio_id: Portfolio ID for the operation (default: "default")

        Returns:
            Operation domain object with all values in integer cents (BRL).

        Raises:
            ValueError: If required fields are missing or conversion fails.
        """
        # Parse dates
        operation_date = parse_date(record.get("operation_date", ""))

        # Parse operation type
        operation_type = normalise_operation_type(record.get("operation_type", ""))

        # Extract asset code
        asset_code = normalise_asset_code(record.get("asset_code"))

        # Parse quantity (in units of asset)
        quantity_str = str(record.get("quantity", "0")).strip()
        quantity = float(quantity_str) if quantity_str else 0.0
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity}")

        # Parse unit price (in quote currency)
        price_str = str(record.get("unit_price", "0")).strip()
        unit_price_numeric = float(price_str) if price_str else 0.0

        # Get quote currency for FX conversion
        quote_currency = str(record.get("quote_currency", "")).strip().upper()
        if not quote_currency:
            # Fallback: extract from pair name
            pair = str(record.get("pair", "")).strip().upper()
            # Guess quote currency from pair (last 3-4 chars)
            if pair.endswith("BRL"):
                quote_currency = "BRL"
            elif pair.endswith("USDT"):
                quote_currency = "USDT"
            elif pair.endswith("BUSD"):
                quote_currency = "BUSD"
            elif pair.endswith("BTC"):
                quote_currency = "BTC"
            elif pair.endswith("BNB"):
                quote_currency = "BNB"
            else:
                quote_currency = "BRL"  # Assume BRL if unsure

        # Parse gross value (in quote currency)
        gross_str = str(record.get("gross_value", "0")).strip()
        gross_numeric = float(gross_str) if gross_str else (quantity * unit_price_numeric)

        # Convert gross value to BRL if needed
        try:
            gross_brl, fx_method = normalize_to_brl(
                gross_numeric, quote_currency, operation_date, self.fx_cache
            )
        except ValueError as exc:
            raise ValueError(f"FX conversion failed: {exc}") from exc

        # Convert gross value to integer cents
        gross_value_cents = int(round(gross_brl * 100))

        # Parse fees (may be in a different currency)
        fee_str = str(record.get("fees", "0")).strip()
        fee_numeric = float(fee_str) if fee_str else 0.0
        fee_unit = str(record.get("fee_unit", "")).strip().upper()

        # Convert fee to BRL cents
        fee_cents = 0
        if fee_numeric > 0:
            # Fees are usually in the base asset (BTC, ETH, etc.)
            # Try to convert to BRL
            fee_currency = fee_unit if fee_unit else asset_code
            try:
                fee_brl, _ = normalize_to_brl(
                    fee_numeric, fee_currency, operation_date, self.fx_cache
                )
                fee_cents = int(round(fee_brl * 100))
            except ValueError:
                # Fee currency not in cache; assume it's the same as quote or skip
                fee_cents = int(round(fee_numeric * 100))

        # Calculate unit price in BRL cents (for cost basis)
        unit_price_brl_cents = int(round((gross_brl / quantity) * 100)) if quantity > 0 else 0

        # Generate deterministic external_id
        external_id = self._generate_external_id(record)

        return Operation(
            portfolio_id=portfolio_id,
            source="binance_csv",
            external_id=external_id,
            asset_code=asset_code,
            asset_type="crypto",
            operation_type=operation_type,
            operation_date=operation_date,
            quantity=quantity,
            unit_price=unit_price_brl_cents,
            gross_value=gross_value_cents,
            fees=fee_cents,
            net_value=gross_value_cents + fee_cents,  # Fees increase cost for buys
            broker="binance",
            account=None,
            raw_data=record,
        )

    @staticmethod
    def _generate_external_id(record: dict[str, Any]) -> str:
        """Generate deterministic external_id from trade data.

        Uses: operation_date + asset_code + operation_type + quantity + gross_value
        """
        key_parts = [
            str(record.get("operation_date", "")),
            str(record.get("asset_code", "")),
            str(record.get("operation_type", "")),
            str(record.get("quantity", "")),
            str(record.get("gross_value", "")),
        ]
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
