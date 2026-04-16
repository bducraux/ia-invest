"""B3 CSV/XLSX extractor for negotiation history exports.

Handles files exported from B3's "Negociacao" report with columns such as:
    Data do Negócio, Tipo de Movimentação, Mercado, Prazo/Vencimento,
    Instituição, Código de Negociação, Quantidade, Preço, Valor
"""

from __future__ import annotations

import csv
import warnings
from pathlib import Path
from typing import Any, cast

import pandas as pd

from extractors.base import BaseExtractor, ExtractionResult

_REQUIRED_COLUMNS = {
    "Data do Negócio",
    "Tipo de Movimentação",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
}


def _normalise_asset_code(raw_code: Any) -> str:
    code = str(raw_code or "").strip().upper()
    # Fracionario codes often come with trailing "F" (e.g. PETR4F)
    if len(code) >= 2 and code.endswith("F") and code[-2].isdigit():
        return code[:-1]
    return code


class B3CsvExtractor(BaseExtractor):
    """Extracts trade records from B3 negotiation CSV/XLSX files."""

    source_type = "b3_csv"

    def can_handle(self, file_path: Path) -> bool:
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            try:
                with file_path.open(encoding="utf-8-sig", newline="") as fh:
                    reader = csv.reader(fh)
                    header = next(reader, [])
                return _REQUIRED_COLUMNS.issubset(set(header))
            except Exception:  # noqa: BLE001
                return False

        if suffix in {".xlsx", ".xls"}:
            try:
                header_df = self._read_excel(file_path, nrows=0)
                return _REQUIRED_COLUMNS.issubset(set(str(c) for c in header_df.columns))
            except Exception:  # noqa: BLE001
                return False

        return False

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            rows = self._read_rows(file_path)
            records, errors = self._parse_rows(rows, file_path.name)
            result.records.extend(records)
            result.errors.extend(errors)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Could not read B3 negotiation file: {exc}",
                }
            )
        return result

    def _read_rows(self, file_path: Path) -> list[dict[str, Any]]:
        suffix = file_path.suffix.lower()
        df = pd.read_csv(file_path) if suffix == ".csv" else self._read_excel(file_path)
        return cast(list[dict[str, Any]], df.to_dict(orient="records"))

    @staticmethod
    def _read_excel(file_path: Path, nrows: int | None = None) -> Any:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Workbook contains no default style, apply openpyxl's default",
                category=UserWarning,
                module="openpyxl.styles.stylesheet",
            )
            return pd.read_excel(file_path, nrows=nrows)

    def _parse_rows(
        self, rows: list[dict[str, Any]], file_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for row_index, row in enumerate(rows):
            if not any(value is not None and str(value).strip() != "" for value in row.values()):
                continue

            try:
                operation_date = str(row.get("Data do Negócio", "")).strip()
                movement_type = str(row.get("Tipo de Movimentação", "")).strip().lower()
                asset_code = _normalise_asset_code(row.get("Código de Negociação"))

                if not operation_date or not movement_type or not asset_code:
                    raise ValueError(
                        "Missing required fields: Data do Negócio, "
                        "Tipo de Movimentação or Código de Negociação."
                    )

                records.append(
                    {
                        "source": self.source_type,
                        "external_id": None,
                        "asset_code": asset_code,
                        "asset_type": None,
                        "operation_type": movement_type,
                        "operation_date": operation_date,
                        "quantity": row.get("Quantidade"),
                        "unit_price": row.get("Preço"),
                        "gross_value": row.get("Valor"),
                        "fees": 0,
                        "broker": row.get("Instituição"),
                        "account": None,
                        "market": row.get("Mercado"),
                        "maturity": row.get("Prazo/Vencimento"),
                        "file_name": file_name,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "parsing",
                        "message": str(exc),
                        "raw_data": row,
                    }
                )

        return records, errors
