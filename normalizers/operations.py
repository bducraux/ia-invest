"""Operations normalizer — converts raw extractor records to Operation objects."""

from __future__ import annotations

from typing import Any

from domain.models import NormalizationError, NormalizationResult, Operation
from normalizers.base import BaseNormalizer
from normalizers.validator import (
    infer_asset_type,
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
                op = self._normalize_one(raw, portfolio_id, import_job_id)
                result.valid.append(op)
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
    ) -> Operation:
        # --- required fields ---
        asset_code = str(raw.get("asset_code") or "").strip().upper()
        if not asset_code:
            raise ValueError("'asset_code' is required.")

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

        return Operation(
            portfolio_id=portfolio_id,
            import_job_id=import_job_id,
            source=str(raw.get("source", "unknown")),
            external_id=raw.get("external_id"),
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

    @staticmethod
    def _safe_date(value: Any) -> str | None:
        if not value or str(value).strip() == "":
            return None
        try:
            return parse_date(str(value))
        except ValueError:
            return None
