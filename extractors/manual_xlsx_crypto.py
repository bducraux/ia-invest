"""Manual XLSX extractor for crypto portfolio bootstrap files."""

from __future__ import annotations

from extractors.manual_xlsx_base import BaseManualXlsxExtractor, excel_serial_to_date, parse_brl

# Some users still type ticker aliases for assets that have been renamed.
_ASSET_CODE_ALIASES: dict[str, str] = {
    "RNDR": "RENDER",
    "MATIC": "POL",  # Polygon renamed MATIC→POL in 2023
}


_excel_serial_to_date = excel_serial_to_date
_parse_brl = parse_brl


class ManualXlsxCryptoExtractor(BaseManualXlsxExtractor):
    """Extracts trade records from manually-prepared crypto XLSX files."""

    source_type = "manual_xlsx_crypto"
    external_id_prefix = "manual_xlsx"
    default_asset_type = "crypto"
    asset_code_aliases = _ASSET_CODE_ALIASES

    def _enrich_record(self, record: dict[str, object], row: tuple[object, ...], col: dict[str, int]) -> None:
        record["quote_currency"] = "BRL"
