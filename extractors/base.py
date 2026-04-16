"""Base extractor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractionResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    source_type: str = ""

    @property
    def total(self) -> int:
        return len(self.records) + len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class BaseExtractor(ABC):
    """Abstract base class for all file extractors.

    Subclasses must implement:
    - ``can_handle(file_path)`` — return True if this extractor supports the file.
    - ``extract(file_path)`` — parse the file and return an ExtractionResult.

    Contract:
    - Extractors do NOT apply business rules or access the database.
    - Parsing errors are recorded in ``ExtractionResult.errors`` and never raise
      exceptions unless the file is completely unreadable.
    - Each record in ``ExtractionResult.records`` is a plain dict with raw values;
      normalizers are responsible for type coercion and validation.
    """

    #: Unique identifier for this extractor, e.g. 'b3_pdf'.
    source_type: str = ""

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this extractor can process the given file."""

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractionResult:
        """Parse the file and return raw records plus any parsing errors."""
