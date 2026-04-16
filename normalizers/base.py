"""Base normalizer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import NormalizationResult


class BaseNormalizer(ABC):
    """Abstract base for all operation normalizers.

    A normalizer receives the raw list of dicts produced by an extractor and
    returns a NormalizationResult with valid Operation objects and any errors.

    Normalizers:
    - Perform type coercion (strings → dates, Decimal, int cents).
    - Run field-level validation (required fields, value ranges).
    - Do NOT access the database or apply deduplication.
    - Do NOT enforce portfolio-level rules (that is the domain service's job).
    """

    @abstractmethod
    def normalize(
        self,
        raw_records: list[dict],
        portfolio_id: str,
        import_job_id: int | None = None,
    ) -> NormalizationResult:
        """Normalize raw extractor records into Operation objects.

        Args:
            raw_records: List of dicts from an extractor.
            portfolio_id: Target portfolio identifier.
            import_job_id: Optional audit job ID to associate with operations.

        Returns:
            NormalizationResult with valid operations and any validation errors.
        """
