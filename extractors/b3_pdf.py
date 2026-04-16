"""B3 PDF extractor — parses broker notes (notas de corretagem) from B3 PDF files.

This is a skeleton implementation.  The actual PDF parsing logic will vary by
broker layout.  The extractor uses pdfplumber to read text content and applies
heuristic pattern matching to extract trade records.

Supported layouts:
- Generic B3 broker note (layout common across most Brazilian brokers)

Each extracted record contains raw string values; normalizers handle
type conversion and validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

try:
    import pdfplumber  # type: ignore[import-untyped,unused-ignore]

    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False


# Regex to detect lines that look like trade records in a broker note.
# Example: "1-BOVESPA  V  PETR4         PN N2    ON  100  28,50  2.850,00  C"
_TRADE_LINE_RE = re.compile(
    r"(?P<market>\S+)\s+"
    r"(?P<op>[VC])\s+"
    r"(?P<asset_code>[A-Z]{4}\d+[A-Z]?\d*)\s+"
    r".*?"
    r"(?P<quantity>[\d.,]+)\s+"
    r"(?P<unit_price>[\d.,]+)\s+"
    r"(?P<gross_value>[\d.,]+)",
    re.IGNORECASE,
)


class B3PdfExtractor(BaseExtractor):
    """Extracts trade records from B3 broker note PDFs."""

    source_type = "b3_pdf"

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)

        if not _PDFPLUMBER_AVAILABLE:
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "dependency",
                    "message": "pdfplumber is not installed. Run: pip install pdfplumber",
                }
            )
            return result

        try:
            records, errors = self._parse_pdf(file_path)
            result.records.extend(records)
            result.errors.extend(errors)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Failed to read PDF: {exc}",
                }
            )

        return result

    def _parse_pdf(
        self, file_path: Path
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        with pdfplumber.open(file_path) as pdf:
            operation_date = self._extract_date(pdf)

            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                for line_num, line in enumerate(text.splitlines()):
                    match = _TRADE_LINE_RE.search(line)
                    if match:
                        try:
                            record = self._parse_trade_line(
                                match, operation_date, file_path
                            )
                            records.append(record)
                        except ValueError as exc:
                            errors.append(
                                {
                                    "row_index": page_num * 1000 + line_num,
                                    "error_type": "parsing",
                                    "message": str(exc),
                                    "raw_data": {"line": line},
                                }
                            )

        return records, errors

    @staticmethod
    def _extract_date(pdf: Any) -> str | None:
        """Try to extract the operation date from the first page."""
        try:
            text = pdf.pages[0].extract_text() or ""
            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
            if date_match:
                return date_match.group(1)
        except Exception:  # noqa: BLE001
            pass
        return None

    @staticmethod
    def _parse_trade_line(
        match: re.Match[str],
        operation_date: str | None,
        file_path: Path,
    ) -> dict[str, Any]:
        op_code = match.group("op").upper()
        operation_type = "buy" if op_code == "C" else "sell"

        return {
            "source": "b3_pdf",
            "external_id": None,
            "asset_code": match.group("asset_code").upper(),
            "asset_type": None,  # normalizer will infer from asset_code
            "operation_type": operation_type,
            "operation_date": operation_date,
            "quantity": match.group("quantity"),
            "unit_price": match.group("unit_price"),
            "gross_value": match.group("gross_value"),
            "fees": "0",
            "broker": None,
            "account": None,
            "file_name": file_path.name,
        }
