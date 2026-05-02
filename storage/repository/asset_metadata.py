"""Repository for the ``asset_metadata`` IRPF registry.

Stores fiscal classification (`asset_class_irpf`) and CNPJ for each asset
code. Used by the IRPF report builder to map operations and positions to
the correct DIRPF section/code.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

AssetClassIrpf = Literal["acao", "fii", "fiagro", "bdr", "etf"]

_VALID_CLASSES: frozenset[str] = frozenset({"acao", "fii", "fiagro", "bdr", "etf"})


@dataclass(frozen=True)
class AssetMetadata:
    asset_code: str
    cnpj: str | None
    asset_class_irpf: AssetClassIrpf
    asset_name_oficial: str | None
    source: str
    notes: str | None = None


def infer_asset_class_irpf(asset_code: str, asset_type: str | None) -> AssetClassIrpf:
    """Best-effort default classification when no metadata is registered.

    V1 maps everything ending in ``11`` to ``fii`` (FIAGRO is reclassified
    manually later via the IA skill).
    """
    code = (asset_code or "").upper().strip()
    atype = (asset_type or "").lower().strip()

    if atype == "fii" or (len(code) >= 5 and code.endswith("11")):
        return "fii"
    if atype == "bdr" or (len(code) == 6 and code[-2:] in {"34", "35"}):
        return "bdr"
    if atype == "etf":
        return "etf"
    return "acao"


class AssetMetadataRepository:
    """Read/write helper for the ``asset_metadata`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, asset_code: str) -> AssetMetadata | None:
        row = self._conn.execute(
            """
            SELECT asset_code, cnpj, asset_class_irpf, asset_name_oficial, source, notes
            FROM asset_metadata
            WHERE asset_code = ?
            """,
            (asset_code.upper(),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_metadata(row)

    def get_many(self, asset_codes: Iterable[str]) -> dict[str, AssetMetadata]:
        codes = sorted({c.upper() for c in asset_codes if c})
        if not codes:
            return {}
        placeholders = ",".join("?" for _ in codes)
        rows = self._conn.execute(
            f"""
            SELECT asset_code, cnpj, asset_class_irpf, asset_name_oficial, source, notes
            FROM asset_metadata
            WHERE asset_code IN ({placeholders})
            """,
            codes,
        ).fetchall()
        return {str(row["asset_code"]): _row_to_metadata(row) for row in rows}

    def list_all(self) -> list[AssetMetadata]:
        rows = self._conn.execute(
            """
            SELECT asset_code, cnpj, asset_class_irpf, asset_name_oficial, source, notes
            FROM asset_metadata
            ORDER BY asset_code
            """
        ).fetchall()
        return [_row_to_metadata(r) for r in rows]

    def list_missing(self, asset_codes: Iterable[str]) -> list[str]:
        codes = sorted({c.upper() for c in asset_codes if c})
        if not codes:
            return []
        present = set(self.get_many(codes).keys())
        return [c for c in codes if c not in present]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert(self, metadata: AssetMetadata, *, commit: bool = True) -> None:
        if metadata.asset_class_irpf not in _VALID_CLASSES:
            raise ValueError(
                f"Invalid asset_class_irpf={metadata.asset_class_irpf!r}; "
                f"must be one of {sorted(_VALID_CLASSES)}"
            )
        self._conn.execute(
            """
            INSERT INTO asset_metadata
                (asset_code, cnpj, asset_class_irpf, asset_name_oficial, source, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(asset_code) DO UPDATE SET
                cnpj               = excluded.cnpj,
                asset_class_irpf   = excluded.asset_class_irpf,
                asset_name_oficial = excluded.asset_name_oficial,
                source             = excluded.source,
                notes              = excluded.notes,
                updated_at         = excluded.updated_at
            """,
            (
                metadata.asset_code.upper(),
                metadata.cnpj,
                metadata.asset_class_irpf,
                metadata.asset_name_oficial,
                metadata.source,
                metadata.notes,
            ),
        )
        if commit:
            self._conn.commit()

    def delete(self, asset_code: str, *, commit: bool = True) -> None:
        self._conn.execute(
            "DELETE FROM asset_metadata WHERE asset_code = ?",
            (asset_code.upper(),),
        )
        if commit:
            self._conn.commit()


def _row_to_metadata(row: sqlite3.Row) -> AssetMetadata:
    return AssetMetadata(
        asset_code=str(row["asset_code"]),
        cnpj=row["cnpj"] if row["cnpj"] is not None else None,
        asset_class_irpf=str(row["asset_class_irpf"]),  # type: ignore[arg-type]
        asset_name_oficial=row["asset_name_oficial"] if row["asset_name_oficial"] is not None else None,
        source=str(row["source"]),
        notes=row["notes"] if row["notes"] is not None else None,
    )
