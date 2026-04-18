"""Gorila XLSX extractor for crypto portfolio exports."""

from __future__ import annotations

from extractors.gorila_base import BaseGorilaXlsxExtractor, excel_serial_to_date, parse_brl

# Gorila uses some ticker aliases that differ from Binance
_ASSET_CODE_ALIASES: dict[str, str] = {
    "RNDR": "RENDER",
    "MATIC": "POL",  # Polygon renamed MATIC→POL in 2023
}


_excel_serial_to_date = excel_serial_to_date
_parse_brl = parse_brl


class GorilaXlsxExtractor(BaseGorilaXlsxExtractor):
    """Extracts trade records from Gorila.io portfolio XLSX exports."""

    source_type = "gorila_xlsx"
    external_id_prefix = "gorila"
    default_asset_type = "crypto"
    asset_code_aliases = _ASSET_CODE_ALIASES

    def _enrich_record(self, record: dict[str, object], row: tuple[object, ...], col: dict[str, int]) -> None:
        record["quote_currency"] = "BRL"
