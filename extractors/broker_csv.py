"""Broker CSV extractor — parses generic broker CSV exports.

Expected CSV columns (case-insensitive, Portuguese or English):
    date / data, asset / ativo, type / tipo, quantity / quantidade,
    price / preco / preço, value / valor, fees / taxas / corretagem,
    broker / corretora, account / conta, id / external_id

Unknown columns are preserved in the raw record for normalizer inspection.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

# Canonical column name mapping (lower-case source header → canonical name)
_COLUMN_MAP: dict[str, str] = {
    "date": "operation_date",
    "data": "operation_date",
    "data operação": "operation_date",
    "data_operacao": "operation_date",
    "asset": "asset_code",
    "ativo": "asset_code",
    "ticker": "asset_code",
    "type": "operation_type",
    "tipo": "operation_type",
    "tipo operação": "operation_type",
    "tipo_operacao": "operation_type",
    "quantity": "quantity",
    "quantidade": "quantity",
    "qtd": "quantity",
    "price": "unit_price",
    "preco": "unit_price",
    "preço": "unit_price",
    "preco_unitario": "unit_price",
    "value": "gross_value",
    "valor": "gross_value",
    "valor_bruto": "gross_value",
    "fees": "fees",
    "taxas": "fees",
    "corretagem": "fees",
    "custos": "fees",
    "broker": "broker",
    "corretora": "broker",
    "account": "account",
    "conta": "account",
    "id": "external_id",
    "external_id": "external_id",
    "order_id": "external_id",
}


class BrokerCsvExtractor(BaseExtractor):
    """Extracts trade records from generic broker CSV files."""

    source_type = "broker_csv"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".csv", ".txt"}

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            text = file_path.read_text(encoding="utf-8-sig")  # handle BOM
            records, errors = self._parse_csv(text, file_path.name)
            result.records.extend(records)
            result.errors.extend(errors)
        except UnicodeDecodeError:
            try:
                text = file_path.read_text(encoding="latin-1")
                records, errors = self._parse_csv(text, file_path.name)
                result.records.extend(records)
                result.errors.extend(errors)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(
                    {
                        "row_index": None,
                        "error_type": "parsing",
                        "message": f"Could not read CSV file: {exc}",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Could not read CSV file: {exc}",
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
                    "message": "CSV has no header row or is empty.",
                }
            )
            return records, errors

        header_map = self._build_header_map(list(reader.fieldnames))

        for row_index, raw_row in enumerate(reader):
            if not any(raw_row.values()):
                continue  # skip blank rows
            try:
                record = self._map_row(raw_row, header_map, file_name)
                records.append(record)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "parsing",
                        "message": str(exc),
                        "raw_data": dict(raw_row),
                    }
                )

        return records, errors

    @staticmethod
    def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
        """Map original CSV headers to canonical field names."""
        return {
            original: _COLUMN_MAP.get(original.lower().strip(), original.lower().strip())
            for original in fieldnames
        }

    @staticmethod
    def _map_row(
        raw_row: dict[str, Any], header_map: dict[str, str], file_name: str
    ) -> dict[str, Any]:
        record: dict[str, Any] = {"source": "broker_csv", "file_name": file_name}
        for original_key, value in raw_row.items():
            canonical = header_map.get(original_key, original_key.lower().strip())
            record[canonical] = value.strip() if isinstance(value, str) else value
        return record
