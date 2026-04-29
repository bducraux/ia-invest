"""Extractor for IBM fundacao previdenciaria monthly PDF statements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pdfplumber

from extractors.base import BaseExtractor, ExtractionResult

_DATE_RANGE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+A\s+(\d{2}/\d{2}/\d{4})")
_PLAN_RE = re.compile(r"Plano:\s*([^\n]+?)\s+CNPJ", re.IGNORECASE)


@dataclass
class _ParsedSnapshot:
    period_start_date: str
    period_end_date: str
    period_month: str
    product_name: str
    previous_quantity: float
    participant_movements_quantity: float
    sponsor_movements_quantity: float
    computed_quantity: float
    quantity: float
    unit_price: float


class PrevidenciaIbmPdfExtractor(BaseExtractor):
    source_type = "previdencia_ibm_pdf"

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".pdf":
            return False
        try:
            first_page = self._extract_page_text(file_path, page_number=0)
        except Exception:
            return False
        upper = first_page.upper()
        return "FUNDACAO PREVIDENCIARIA IBM" in self._strip_accents(upper)

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            parsed = self._parse_snapshot(file_path)
        except ValueError as exc:
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": str(exc),
                    "raw_data": {"file": file_path.name},
                }
            )
            return result

        unit_price_cents = int(round(parsed.unit_price * 100))
        quantity = parsed.quantity
        market_value_cents = int(round(quantity * unit_price_cents))

        result.records.append(
            {
                "asset_code": "PREV_IBM_CD",
                "product_name": parsed.product_name,
                "period_start_date": parsed.period_start_date,
                "period_end_date": parsed.period_end_date,
                "period_month": parsed.period_month,
                "quantity": quantity,
                "unit_price_cents": unit_price_cents,
                "market_value_cents": market_value_cents,
                "source_file": file_path.name,
                "raw_data": {
                    "previous_quantity": parsed.previous_quantity,
                    "participant_movements_quantity": parsed.participant_movements_quantity,
                    "sponsor_movements_quantity": parsed.sponsor_movements_quantity,
                    "computed_quantity": parsed.computed_quantity,
                },
            }
        )
        return result

    def extract_period_month(self, file_path: Path) -> str:
        return self._parse_snapshot(file_path).period_month

    def _parse_snapshot(self, file_path: Path) -> _ParsedSnapshot:
        pages = self._extract_all_pages_text(file_path)
        if not pages:
            raise ValueError("Could not read PDF text")

        all_text = "\n".join(pages)
        date_match = _DATE_RANGE_RE.search(all_text)
        if not date_match:
            raise ValueError("Could not parse statement period")

        period_start_date = self._to_iso(date_match.group(1))
        period_end_date = self._to_iso(date_match.group(2))
        period_month = period_end_date[:7]

        plan_match = _PLAN_RE.search(all_text)
        product_name = (
            plan_match.group(1).strip().replace("  ", " ") if plan_match else "IBM CD"
        )

        section_1 = self._section_between(all_text, "1)", "2)")
        section_2 = self._section_between(all_text, "2)", "3)")
        section_3 = self._section_between(all_text, "3)", "4)")
        section_5 = self._section_between(all_text, "5)", "OBS:") or self._section_from(all_text, "5)")

        previous_quantity = self._extract_previous_quantity(section_1)
        participant_qtd, _ = self._extract_movements(section_2)
        sponsor_qtd, _ = self._extract_movements(section_3)
        computed_quantity = previous_quantity + participant_qtd + sponsor_qtd

        qty_current_total, unit_price = self._extract_current_total(section_5)
        final_quantity = qty_current_total if qty_current_total is not None else computed_quantity
        if unit_price is None:
            raise ValueError("Could not parse current unit price")

        return _ParsedSnapshot(
            period_start_date=period_start_date,
            period_end_date=period_end_date,
            period_month=period_month,
            product_name=product_name,
            previous_quantity=previous_quantity,
            participant_movements_quantity=participant_qtd,
            sponsor_movements_quantity=sponsor_qtd,
            computed_quantity=computed_quantity,
            quantity=final_quantity,
            unit_price=unit_price,
        )

    @staticmethod
    def _to_iso(br_date: str) -> str:
        return datetime.strptime(br_date, "%d/%m/%Y").date().isoformat()

    @staticmethod
    def _extract_all_pages_text(file_path: Path) -> list[str]:
        pages: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                pages.append(txt)
        return pages

    @staticmethod
    def _extract_page_text(file_path: Path, page_number: int) -> str:
        with pdfplumber.open(file_path) as pdf:
            if page_number >= len(pdf.pages):
                return ""
            return pdf.pages[page_number].extract_text() or ""

    @staticmethod
    def _section_between(text: str, start: str, end: str) -> str:
        start_idx = text.find(start)
        if start_idx < 0:
            return ""
        end_idx = text.find(end, start_idx + len(start))
        if end_idx < 0:
            return text[start_idx:]
        return text[start_idx:end_idx]

    @staticmethod
    def _section_from(text: str, start: str) -> str:
        start_idx = text.find(start)
        if start_idx < 0:
            return ""
        return text[start_idx:]

    def _extract_previous_quantity(self, section: str) -> float:
        # Expected row style:
        # Conta Saldo Anterior ... 9.064,5884 47,4615 430.218,79
        for line in section.splitlines():
            if "CONTA SALDO ANTERIOR" not in self._strip_accents(line.upper()):
                continue
            values = self._extract_numeric_tokens(line)
            if len(values) < 3:
                continue
            return self._parse_brl_number(values[-3])
        raise ValueError("Could not parse previous quantity from section 1")

    def _extract_movements(self, section: str) -> tuple[float, float | None]:
        quantity_sum = 0.0
        last_unit_price: float | None = None
        for line in section.splitlines():
            if "TOTAL:" in line.upper():
                continue
            values = self._extract_numeric_tokens(line)
            # Movement rows with quantity include at least 3 trailing numbers:
            # qtd_cotas, valor_cota, valor_rs
            if len(values) >= 3:
                quantity_sum += self._parse_brl_number(values[-3])
                last_unit_price = self._parse_brl_number(values[-2])
        return quantity_sum, last_unit_price

    def _extract_current_total(self, section: str) -> tuple[float | None, float | None]:
        qty_sum = 0.0
        found_rows = 0
        last_unit_price: float | None = None
        for line in section.splitlines():
            normalized = self._strip_accents(line.upper())
            if "CONTA PARTICIPANTE" not in normalized and "CONTA PATROCINADORA" not in normalized:
                continue
            values = self._extract_numeric_tokens(line)
            if len(values) < 3:
                continue
            qty_sum += self._parse_brl_number(values[-3])
            last_unit_price = self._parse_brl_number(values[-2])
            found_rows += 1

        if found_rows == 0:
            return None, None
        return qty_sum, last_unit_price

    @staticmethod
    def _extract_numeric_tokens(line: str) -> list[str]:
        return re.findall(r"\d[\d\.]*,\d+", line)

    @staticmethod
    def _parse_brl_number(value: str) -> float:
        return float(value.replace(".", "").replace(",", "."))

    @staticmethod
    def _strip_accents(text: str) -> str:
        replacements = {
            "A": "A",
            "E": "E",
            "I": "I",
            "O": "O",
            "U": "U",
            "C": "C",
            "a": "a",
            "e": "e",
            "i": "i",
            "o": "o",
            "u": "u",
            "c": "c",
            "Á": "A",
            "À": "A",
            "Ã": "A",
            "Â": "A",
            "É": "E",
            "Ê": "E",
            "Í": "I",
            "Ó": "O",
            "Ô": "O",
            "Õ": "O",
            "Ú": "U",
            "Ç": "C",
            "á": "a",
            "à": "a",
            "ã": "a",
            "â": "a",
            "é": "e",
            "ê": "e",
            "í": "i",
            "ó": "o",
            "ô": "o",
            "õ": "o",
            "ú": "u",
            "ç": "c",
        }
        return "".join(replacements.get(ch, ch) for ch in text)
