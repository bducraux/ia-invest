"""Extractors package.

Extractors parse raw input files (PDFs, CSVs, etc.) into lists of raw dicts.
They do NOT apply business rules; that is the job of normalizers.

Registry maps source type names (as declared in portfolio.yml) to extractor
classes.  Use ``get_extractor(source_type)`` to retrieve the right one.
"""

from __future__ import annotations

from extractors.b3_csv import B3CsvExtractor
from extractors.base import BaseExtractor, ExtractionResult
from extractors.binance_csv import BinanceCsvExtractor
from extractors.binance_simple_earn import BinanceSimpleEarnExtractor
from extractors.broker_csv import BrokerCsvExtractor
from extractors.gorila_b3_xlsx import GorilaB3XlsxExtractor
from extractors.gorila_xlsx import GorilaXlsxExtractor

_REGISTRY: dict[str, type[BaseExtractor]] = {
    "b3_csv": B3CsvExtractor,
    "broker_csv": BrokerCsvExtractor,
    "binance_csv": BinanceCsvExtractor,
    "binance_simple_earn": BinanceSimpleEarnExtractor,
    "gorila_b3_xlsx": GorilaB3XlsxExtractor,
    "gorila_xlsx": GorilaXlsxExtractor,
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
    "GorilaB3XlsxExtractor",
    "GorilaXlsxExtractor",
    "get_extractor",
    "list_source_types",
]
