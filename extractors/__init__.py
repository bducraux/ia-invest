"""Extractors package.

Extractors parse raw input files (PDFs, CSVs, etc.) into lists of raw dicts.
They do NOT apply business rules; that is the job of normalizers.

Registry maps source type names (as declared in portfolio.yml) to extractor
classes.  Use ``get_extractor(source_type)`` to retrieve the right one.
"""

from __future__ import annotations

from extractors.b3_pdf import B3PdfExtractor
from extractors.base import BaseExtractor, ExtractionResult
from extractors.binance_csv import BinanceCsvExtractor
from extractors.broker_csv import BrokerCsvExtractor

_REGISTRY: dict[str, type[BaseExtractor]] = {
    "b3_pdf": B3PdfExtractor,
    "broker_csv": BrokerCsvExtractor,
    "binance_csv": BinanceCsvExtractor,
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
    "B3PdfExtractor",
    "BrokerCsvExtractor",
    "BinanceCsvExtractor",
    "get_extractor",
    "list_source_types",
]
