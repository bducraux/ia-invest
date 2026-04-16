"""Binance CSV extractor — parses Binance trade history CSV exports.

Binance CSV columns (as exported from the web):
    Date(UTC), Pair, Side, Price, Executed, Amount, Fee

Date format: YYYY-MM-DD HH:MM:SS

Side values: BUY, SELL

The "Pair" column contains the trading pair (e.g., BTCUSDT, ETHBRL).
We extract the base asset from the pair using heuristics.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

# Known quote currencies to strip from pair names to get base asset
_QUOTE_CURRENCIES = {"USDT", "BUSD", "BRL", "BTC", "ETH", "BNB", "USD", "EUR"}


def _parse_base_asset(pair: str) -> str:
    """Extract base asset code from a trading pair string."""
    pair = pair.upper()
    for quote in sorted(_QUOTE_CURRENCIES, key=len, reverse=True):
        if pair.endswith(quote):
            return pair[: -len(quote)]
    # fallback: return as-is
    return pair


class BinanceCsvExtractor(BaseExtractor):
    """Extracts trade records from Binance trade history CSV files."""

    source_type = "binance_csv"

    # Binance CSV headers (exact match expected)
    _REQUIRED_COLUMNS = {"Date(UTC)", "Pair", "Side", "Price", "Executed", "Amount", "Fee"}

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".csv":
            return False
        # Peek at the header to confirm it looks like a Binance export
        try:
            with file_path.open(encoding="utf-8-sig") as fh:
                first_line = fh.readline()
            return "Date(UTC)" in first_line and "Pair" in first_line
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

        for row_index, row in enumerate(reader):
            if not any(row.values()):
                continue
            try:
                record = self._map_row(row, file_name)
                records.append(record)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "parsing",
                        "message": str(exc),
                        "raw_data": dict(row),
                    }
                )

        return records, errors

    @staticmethod
    def _map_row(row: dict[str, Any], file_name: str) -> dict[str, Any]:
        pair = str(row.get("Pair", "")).strip()
        base_asset = _parse_base_asset(pair)
        side = str(row.get("Side", "")).strip().upper()

        # Extract numeric value from "Executed" (e.g. "0.5 BTC" → "0.5")
        executed_raw = str(row.get("Executed", "0")).strip()
        executed_match = re.match(r"([\d.,]+)", executed_raw)
        executed = executed_match.group(1) if executed_match else "0"

        fee_raw = str(row.get("Fee", "0")).strip()
        fee_match = re.match(r"([\d.,]+)", fee_raw)
        fee = fee_match.group(1) if fee_match else "0"

        # Date: "2023-01-15 10:30:00" → "2023-01-15"
        date_raw = str(row.get("Date(UTC)", "")).strip()
        operation_date = date_raw[:10] if len(date_raw) >= 10 else date_raw

        return {
            "source": "binance_csv",
            "external_id": None,
            "asset_code": base_asset,
            "asset_type": "crypto",
            "operation_type": "buy" if side == "BUY" else "sell",
            "operation_date": operation_date,
            "quantity": executed,
            "unit_price": str(row.get("Price", "0")).strip(),
            "gross_value": str(row.get("Amount", "0")).strip(),
            "fees": fee,
            "broker": "binance",
            "account": None,
            "pair": pair,
            "file_name": file_name,
        }
