"""Binance CSV extractor — parses Binance spot trade history CSV exports.

Supports both English (Date(UTC), Pair, Side, Price, Executed, Amount, Fee)
and Portuguese (Tempo, Par, Lado, Preço, Executado, Quantidade, Taxa) headers.

Date format: yy-mm-dd HH:MM:SS (e.g., 26-04-13 21:13:14)

Side values: BUY, SELL

Pair examples: BTCBRL, ETHUSDT, BNBBUSD, ETHBTC (quote currency is always last).

Processing:
1. Remove exact duplicates (all columns identical).
2. Aggregate split fills: same timestamp + pair + side + price → one record.
3. Parse quantities with unit suffixes (e.g., "0.5 BTC" → 0.5, unit "BTC").
4. Normalize dates to ISO 8601 (YYYY-MM-DD).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

# Known quote currencies to strip from pair names to get base asset
_QUOTE_CURRENCIES = {"USDT", "BUSD", "BRL", "BTC", "ETH", "BNB", "USD", "EUR"}

# Header mappings: [English, Portuguese]
_HEADER_MAP = {
    "Tempo": "Date(UTC)",
    "Par": "Pair",
    "Lado": "Side",
    "Preço": "Price",
    "Executado": "Executed",
    "Quantidade": "Amount",
    "Taxa": "Fee",
}


def _parse_base_asset(pair: str) -> str:
    """Extract base asset code from a trading pair string."""
    pair = pair.upper().strip()
    for quote in sorted(_QUOTE_CURRENCIES, key=len, reverse=True):
        if pair.endswith(quote) and len(pair) > len(quote):
            return pair[: -len(quote)]
    return pair


def _normalize_date(date_str: str) -> str:
    """Convert Binance date format to ISO 8601 (YYYY-MM-DD).

    Supports:
        - yy-mm-dd (e.g., "26-04-13")
        - YYYY-MM-DD (e.g., "2023-06-01")
    Time component is always ignored.
    """
    raw = str(date_str).strip()
    if not raw:
        raise ValueError("Date is empty")

    # Take date part only (first 8-10 chars)
    date_part = raw.split()[0] if " " in raw else raw[:10]

    # Try YYYY-MM-DD first (English format)
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try yy-mm-dd (Portuguese format)
    try:
        dt = datetime.strptime(date_part, "%y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError as err:
        raise ValueError(f"Cannot parse date '{raw}' as YYYY-MM-DD or yy-mm-dd") from err


def _normalize_timestamp(date_str: str) -> str:
    """Normalize Binance datetime string to ``YYYY-MM-DD HH:MM:SS``.

    Supports both two-digit and four-digit year exports.
    """
    raw = str(date_str).strip()
    if not raw:
        raise ValueError("Date is empty")

    for fmt in ("%Y-%m-%d %H:%M:%S", "%y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    raise ValueError(f"Cannot parse timestamp '{raw}'")


def _extract_numeric_with_unit(value_str: str) -> tuple[float, str | None]:
    """Extract numeric value and optional unit suffix.

    Examples:
        "0.5 BTC" → (0.5, "BTC")
        "0.00023BTC" → (0.00023, "BTC")
        "1248.02955BRL" → (1248.02955, "BRL")
        "0.5" → (0.5, None)
    """
    raw = str(value_str).strip()
    if not raw:
        raise ValueError("Value is empty")

    # Extract leading numeric part
    match = re.match(r"([\d.]+)", raw)
    if not match:
        raise ValueError(f"No numeric value in '{raw}'")

    numeric_str = match.group(1)
    unit = None

    # Check for unit suffix after the number
    remainder = raw[len(numeric_str):].strip()
    if remainder and not remainder.startswith(",") and not remainder.startswith("."):
        unit = remainder.upper()

    try:
        numeric = float(numeric_str)
    except ValueError as err:
        raise ValueError(f"Cannot parse number '{numeric_str}'") from err

    return numeric, unit


class BinanceCsvExtractor(BaseExtractor):
    """Extracts and aggregates spot trades from Binance CSV exports."""

    source_type = "binance_csv"

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".csv":
            return False
        try:
            with file_path.open(encoding="utf-8-sig") as fh:
                first_line = fh.readline()
            # Accept either English or Portuguese headers
            return (
                ("Date(UTC)" in first_line and "Pair" in first_line)
                or ("Tempo" in first_line and "Par" in first_line)
            )
        except Exception:  # noqa: BLE001
            return False

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            text = file_path.read_text(encoding="utf-8-sig")
            records, errors = self._parse_csv(text, file_path.name)
            result.records.extend(records)
            result.errors.extend(errors)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Could not read Binance CSV: {exc}",
                }
            )
        return result

    def _parse_csv(
        self, text: str, file_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": "CSV is empty or has no header row.",
                }
            )
            return records, errors

        # Normalize header names (Portuguese → English)
        normalized_fieldnames = [
            _HEADER_MAP.get(fn, fn) if fn else fn
            for fn in reader.fieldnames
        ]
        reader.fieldnames = normalized_fieldnames

        # Collect all rows, then deduplicate and aggregate
        all_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(reader):
            if not any(row.values()):
                continue
            try:
                mapped = self._map_row(row, file_name)
                all_rows.append(mapped)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "parsing",
                        "message": str(exc),
                        "raw_data": dict(row),
                    }
                )

        # Step 1: Remove exact duplicates (all relevant mapped columns identical)
        seen = set()
        deduped = []
        for row in all_rows:
            key = self._dedup_key(row)
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        # Step 2: Aggregate split fills (same timestamp + pair + side + price)
        aggregated = self._aggregate_split_fills(deduped)

        # Generate deterministic external_id from full operation fingerprint.
        for row in aggregated:
            row["external_id"] = self._generate_external_id(row)

        records.extend(aggregated)
        return records, errors

    @staticmethod
    def _dedup_key(row: dict[str, Any]) -> tuple[Any, ...]:
        """Key for exact duplicate detection inside one file.

        Duplicate means same values across all relevant operation columns.
        """
        return (
            row.get("source"),
            row.get("event_timestamp"),
            row.get("operation_date"),
            row.get("pair"),
            row.get("asset_code"),
            row.get("asset_type"),
            row.get("operation_type"),
            row.get("quantity"),
            row.get("unit_price"),
            row.get("gross_value"),
            row.get("fees"),
            row.get("broker"),
            row.get("account"),
            row.get("quote_currency"),
            row.get("quantity_unit"),
            row.get("fee_unit"),
            row.get("file_name"),
        )

    @staticmethod
    def _generate_external_id(row: dict[str, Any]) -> str:
        """Deterministic ID using all operation-defining values.

        This ensures DB duplicate detection only matches truly equal rows.
        """
        parts = [
            str(row.get("source", "")),
            str(row.get("event_timestamp", "")),
            str(row.get("pair", "")),
            str(row.get("asset_code", "")),
            str(row.get("operation_type", "")),
            str(row.get("quantity", "")),
            str(row.get("unit_price", "")),
            str(row.get("gross_value", "")),
            str(row.get("fees", "")),
            str(row.get("quote_currency", "")),
            str(row.get("quantity_unit", "")),
            str(row.get("fee_unit", "")),
        ]
        key = "|".join(parts)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @staticmethod
    def _aggregate_split_fills(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group split fills by (timestamp + pair + side + price) and aggregate quantities/fees."""
        groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)

        for row in rows:
            key = (
                row.get("event_timestamp", ""),
                row.get("pair", ""),
                row.get("operation_type", ""),
                row.get("unit_price", ""),
                row.get("quote_currency", ""),  # to distinguish BRL vs USDT
            )
            groups[key].append(row)

        aggregated = []
        for group in groups.values():
            if len(group) == 1:
                aggregated.append(group[0])
            else:
                # Aggregate multiple fills with same key
                first = group[0]
                agg_qty = sum(float(r.get("quantity", 0)) for r in group)
                agg_gross = sum(float(r.get("gross_value", 0)) for r in group)
                agg_fees = sum(float(r.get("fees", 0)) for r in group)

                aggregated_row = dict(first)
                aggregated_row["quantity"] = str(agg_qty)
                aggregated_row["gross_value"] = str(agg_gross)
                aggregated_row["fees"] = str(agg_fees)
                aggregated_row["_aggregated"] = True
                aggregated_row["_fill_count"] = len(group)
                aggregated.append(aggregated_row)

        return aggregated

    @staticmethod
    def _map_row(row: dict[str, Any], file_name: str) -> dict[str, Any]:
        pair = str(row.get("Pair", "")).strip().upper()
        base_asset = _parse_base_asset(pair)
        side = str(row.get("Side", "")).strip().upper()

        # Parse date (yy-mm-dd HH:MM:SS format)
        date_raw = str(row.get("Date(UTC)", "")).strip()
        event_timestamp = _normalize_timestamp(date_raw)
        operation_date = _normalize_date(date_raw)

        # Parse Executed (quantity of base asset with unit, e.g., "0.5 BTC")
        executed_raw = str(row.get("Executed", "0")).strip()
        try:
            quantity_numeric, quantity_unit = _extract_numeric_with_unit(executed_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid Executed field: {exc}") from exc

        # Parse Amount (gross value in quote currency, e.g., "1248.02955BRL")
        amount_raw = str(row.get("Amount", "0")).strip()
        try:
            gross_numeric, quote_currency = _extract_numeric_with_unit(amount_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid Amount field: {exc}") from exc

        # If quote currency not in Amount field, infer from pair
        if not quote_currency:
            quote_currency = pair[len(base_asset):] if pair.startswith(base_asset) else None

        # Parse Price (unit price, usually just numeric)
        price_raw = str(row.get("Price", "0")).strip()
        try:
            price_numeric, _ = _extract_numeric_with_unit(price_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid Price field: {exc}") from exc

        # Parse Fee (may have unit suffix, e.g., "0.0000028BTC")
        fee_raw = str(row.get("Fee", "0")).strip()
        try:
            fee_numeric, fee_unit = _extract_numeric_with_unit(fee_raw)
        except ValueError:
            # Fee might be truly empty, default to 0
            fee_numeric = 0.0
            fee_unit = None

        return {
            "source": "binance_csv",
            "external_id": None,  # Filled deterministically after dedup/aggregation
            "asset_code": base_asset,
            "asset_type": "crypto",
            "operation_type": "buy" if side == "BUY" else "sell",
            "event_timestamp": event_timestamp,
            "operation_date": operation_date,
            "quantity": str(quantity_numeric),
            "unit_price": str(price_numeric),
            "gross_value": str(gross_numeric),
            "fees": str(fee_numeric),
            "broker": "binance",
            "account": None,
            "pair": pair,
            "quote_currency": quote_currency,  # For aggregation logic
            "quantity_unit": quantity_unit,  # Original unit (should match base_asset)
            "fee_unit": fee_unit,  # Fee currency
            "file_name": file_name,
            "raw_data": dict(row),
        }
