"""Operations normalizer — converts raw extractor records to Operation objects."""

from __future__ import annotations

import hashlib
from typing import Any

from domain.models import NormalizationError, NormalizationResult, Operation
from normalizers.base import BaseNormalizer
from normalizers.validator import (
    infer_asset_type,
    normalise_asset_code,
    normalise_operation_type,
    parse_date,
    parse_monetary_cents,
    parse_quantity,
)


class OperationNormalizer(BaseNormalizer):
    """Normalizes raw records from any extractor into Operation domain objects.

    This normalizer handles:
    - Date parsing (multiple formats → ISO 8601)
    - Monetary value parsing (Brazilian and US formatting → integer cents)
    - Quantity parsing
    - Operation type aliasing
    - Asset type inference (when not provided by the extractor)
    - Required field validation
    """

    def normalize(
        self,
        raw_records: list[dict[str, Any]],
        portfolio_id: str,
        import_job_id: int | None = None,
    ) -> NormalizationResult:
        result = NormalizationResult()

        for row_index, raw in enumerate(raw_records):
            try:
                ops = self._normalize_one(raw, portfolio_id, import_job_id)
                result.valid.extend(ops)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(
                    NormalizationError(
                        row_index=row_index,
                        error_type="validation",
                        message=str(exc),
                        raw_data=raw,
                    )
                )

        return result

    def _normalize_one(
        self,
        raw: dict[str, Any],
        portfolio_id: str,
        import_job_id: int | None,
    ) -> list[Operation]:
        # --- required fields ---
        asset_code = normalise_asset_code(raw.get("asset_code"))

        operation_date = parse_date(raw.get("operation_date"))
        operation_type = normalise_operation_type(str(raw.get("operation_type", "")))
        quantity = parse_quantity(raw.get("quantity"))

        # --- financial values ---
        unit_price = parse_monetary_cents(raw.get("unit_price"), "unit_price")
        gross_value = parse_monetary_cents(raw.get("gross_value"), "gross_value")
        fees = parse_monetary_cents(raw.get("fees", 0), "fees")

        # Derive gross_value or unit_price if one is missing
        if gross_value == 0 and unit_price > 0 and quantity > 0:
            gross_value = round(unit_price * quantity)
        if unit_price == 0 and gross_value > 0 and quantity > 0:
            unit_price = round(gross_value / quantity)

        # --- asset type ---
        asset_type = str(raw.get("asset_type") or "").strip().lower()
        if not asset_type:
            asset_type = infer_asset_type(asset_code)

        source = str(raw.get("source", "unknown"))
        external_id = raw.get("external_id")
        if external_id is None or str(external_id).strip() == "":
            external_id = self._build_fallback_external_id(
                source=source,
                asset_code=asset_code,
                operation_type=operation_type,
                operation_date=operation_date,
                quantity=quantity,
                unit_price=unit_price,
                gross_value=gross_value,
                fees=fees,
                asset_type=asset_type,
                broker=raw.get("broker"),
                account=raw.get("account"),
                settlement_date=self._safe_date(raw.get("settlement_date")),
            )

        main_op = Operation(
            portfolio_id=portfolio_id,
            import_job_id=import_job_id,
            source=source,
            external_id=external_id,
            asset_code=asset_code,
            asset_type=asset_type,
            asset_name=raw.get("asset_name"),
            operation_type=operation_type,
            operation_date=operation_date,
            settlement_date=self._safe_date(raw.get("settlement_date")),
            quantity=quantity,
            unit_price=unit_price,
            gross_value=gross_value,
            fees=fees,
            broker=raw.get("broker"),
            account=raw.get("account"),
            notes=raw.get("notes"),
            raw_data=raw,
        )

        quote_legs = self._build_quote_leg_if_needed(
            raw=raw,
            main_op=main_op,
            portfolio_id=portfolio_id,
            import_job_id=import_job_id,
        )
        return [main_op, *quote_legs]

    def _build_quote_leg_if_needed(
        self,
        *,
        raw: dict[str, Any],
        main_op: Operation,
        portfolio_id: str,
        import_job_id: int | None,
    ) -> list[Operation]:
        """Build quote-asset leg for Binance spot trades.

        Example:
            BUY ETHUSDT => +ETH (main op), -USDT (quote leg)
            SELL ETHUSDT => -ETH (main op), +USDT (quote leg)
        """
        if main_op.source != "binance_csv":
            return []

        quote_currency_raw = str(raw.get("quote_currency") or "").strip()
        if not quote_currency_raw:
            return []

        quote_asset = normalise_asset_code(quote_currency_raw)
        # Avoid creating BRL/USD/EUR pseudo positions from quote legs.
        if quote_asset in {"BRL", "USD", "EUR"}:
            return []

        if quote_asset == main_op.asset_code:
            return []

        quote_qty = parse_quantity(raw.get("gross_value"))
        if quote_qty <= 0:
            return []

        fee_in_quote = 0.0
        fee_unit = str(raw.get("fee_unit") or "").strip().upper()
        if fee_unit and normalise_asset_code(fee_unit) == quote_asset:
            fee_in_quote = parse_quantity(raw.get("fees", 0))

        if main_op.operation_type == "buy":
            # Buying base asset spends quote asset.
            qty = quote_qty + fee_in_quote
            op_type = "transfer_out"
        elif main_op.operation_type == "sell":
            # Selling base asset receives quote asset (minus quote-denominated fee).
            qty = max(quote_qty - fee_in_quote, 0.0)
            op_type = "transfer_in"
        else:
            return []

        if qty <= 0:
            return []

        quote_raw = dict(raw)
        quote_raw["quote_leg"] = True
        quote_raw["quote_leg_of_external_id"] = main_op.external_id

        quote_external_id = (
            f"{main_op.external_id}:quote"
            if main_op.external_id
            else self._build_fallback_external_id(
                source=f"{main_op.source}:quote",
                asset_code=quote_asset,
                operation_type=op_type,
                operation_date=main_op.operation_date,
                quantity=qty,
                unit_price=0,
                gross_value=0,
                fees=0,
                asset_type="crypto",
                broker=main_op.broker,
                account=main_op.account,
                settlement_date=main_op.settlement_date,
            )
        )

        quote_op = Operation(
            portfolio_id=portfolio_id,
            import_job_id=import_job_id,
            source=main_op.source,
            external_id=quote_external_id,
            asset_code=quote_asset,
            asset_type="crypto",
            asset_name=None,
            operation_type=op_type,
            operation_date=main_op.operation_date,
            settlement_date=main_op.settlement_date,
            quantity=qty,
            # Keep monetary fields zero to avoid fake BRL valuation for quote legs.
            unit_price=0,
            gross_value=0,
            fees=0,
            broker=main_op.broker,
            account=main_op.account,
            notes="Auto-generated quote leg from Binance spot trade",
            raw_data=quote_raw,
        )
        return [quote_op]

    @staticmethod
    def _build_fallback_external_id(
        *,
        source: str,
        asset_code: str,
        operation_type: str,
        operation_date: str,
        quantity: float,
        unit_price: int,
        gross_value: int,
        fees: int,
        asset_type: str,
        broker: Any,
        account: Any,
        settlement_date: str | None,
    ) -> str:
        parts = [
            source,
            asset_code,
            operation_type,
            operation_date,
            f"{quantity:.12f}",
            str(unit_price),
            str(gross_value),
            str(fees),
            asset_type,
            str(broker or ""),
            str(account or ""),
            str(settlement_date or ""),
        ]
        key = "|".join(parts)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @staticmethod
    def _safe_date(value: Any) -> str | None:
        if not value or str(value).strip() == "":
            return None
        try:
            return parse_date(str(value))
        except ValueError:
            return None
