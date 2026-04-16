"""Deduplication service — detects duplicate operations before persistence."""

from __future__ import annotations

from domain.models import Operation


class DeduplicationService:
    """Filters out operations that are duplicates of each other within a batch.

    Duplicates that already exist in the database are handled by the UNIQUE
    constraint in the operations table (sqlite3.IntegrityError).  This service
    handles intra-batch deduplication (same file imported twice, overlapping
    exports, etc.).
    """

    DEFAULT_KEYS = (
        "portfolio_id",
        "source",
        "external_id",
        "operation_date",
        "asset_code",
        "operation_type",
    )

    def deduplicate(
        self,
        operations: list[Operation],
        keys: list[str] | None = None,
    ) -> tuple[list[Operation], list[Operation]]:
        """Remove duplicate operations within *operations*.

        Args:
            operations: Candidate list to deduplicate.
            keys: Fields to use as deduplication key.  Defaults to DEFAULT_KEYS.

        Returns:
            (unique, duplicates) — two lists; unique contains the first
            occurrence of each key, duplicates contains the rest.
        """
        effective_keys = keys or list(self.DEFAULT_KEYS)
        seen: set[tuple[object, ...]] = set()
        unique: list[Operation] = []
        duplicates: list[Operation] = []

        for op in operations:
            key = self._make_key(op, effective_keys)
            if key in seen:
                duplicates.append(op)
            else:
                seen.add(key)
                unique.append(op)

        return unique, duplicates

    @staticmethod
    def _make_key(op: Operation, keys: list[str]) -> tuple[object, ...]:
        return tuple(getattr(op, k, None) for k in keys)
