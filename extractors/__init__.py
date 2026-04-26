"""Extractors package.

Extractors parse raw input files (PDFs, CSVs, etc.) into lists of raw dicts.
They do NOT apply business rules; that is the job of normalizers.

Registry maps source type names (as declared in portfolio.yml) to extractor
classes.  Use ``get_extractor(source_type)`` to retrieve the right one.
"""

from __future__ import annotations

from extractors.avenue_apex_pdf import AvenueApexPdfExtractor
from extractors.b3_csv import B3CsvExtractor
from extractors.base import BaseExtractor, ExtractionResult
from extractors.binance_csv import BinanceCsvExtractor
from extractors.binance_simple_earn import BinanceSimpleEarnExtractor
from extractors.broker_csv import BrokerCsvExtractor
from extractors.manual_xlsx_b3 import ManualXlsxB3Extractor
from extractors.manual_xlsx_crypto import ManualXlsxCryptoExtractor
from extractors.previdencia_ibm_pdf import PrevidenciaIbmPdfExtractor

_REGISTRY: dict[str, type[BaseExtractor]] = {
    "b3_csv": B3CsvExtractor,
    "broker_csv": BrokerCsvExtractor,
    "binance_csv": BinanceCsvExtractor,
    "binance_simple_earn": BinanceSimpleEarnExtractor,
    "avenue_apex_pdf": AvenueApexPdfExtractor,
    "manual_xlsx_b3": ManualXlsxB3Extractor,
    "manual_xlsx_crypto": ManualXlsxCryptoExtractor,
    "previdencia_ibm_pdf": PrevidenciaIbmPdfExtractor,
}


def get_extractor(source_type: str) -> BaseExtractor:
    """Return an extractor instance for the given source type.

    Raises:
        KeyError: if no extractor is registered for the given source type.
    """
    cls = _REGISTRY[source_type]
    return cls()


def list_source_types() -> list[str]:
    """Return all registered source type names."""
    return list(_REGISTRY.keys())


__all__ = [
    "BaseExtractor",
    "ExtractionResult",
    "B3CsvExtractor",
    "BrokerCsvExtractor",
    "BinanceCsvExtractor",
    "AvenueApexPdfExtractor",
    "ManualXlsxB3Extractor",
    "ManualXlsxCryptoExtractor",
    "PrevidenciaIbmPdfExtractor",
    "get_extractor",
    "list_source_types",
]
