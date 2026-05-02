"""Repository for the ``asset_metadata`` cross-domain registry.

Stores fiscal/structural classification (`asset_class`), CNPJ, sector hints
and official RI page for each asset code. Used by the IRPF report builder,
the sector exposure analytics, and the asset-metadata-enrich skill.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

AssetClass = Literal[
    "acao", "fii", "fiagro", "bdr", "etf", "cripto", "stocks"
]

_VALID_CLASSES: frozenset[str] = frozenset(
    {"acao", "fii", "fiagro", "bdr", "etf", "cripto", "stocks"}
)

# asset_type → asset_class hints used by `infer_asset_class`.
_INTERNATIONAL_ASSET_TYPES: frozenset[str] = frozenset(
    {"stock_us", "etf_us", "reit_us", "bdr_us"}
)


@dataclass(frozen=True)
class AssetMetadata:
    asset_code: str
    cnpj: str | None
    asset_class: AssetClass
    asset_name_oficial: str | None
    source: str
    notes: str | None = None
    sector_category: str | None = None
    sector_subcategory: str | None = None
    site_ri: str | None = None
    data_source: str | None = None
    last_synced_at: str | None = None


def infer_asset_class(asset_code: str, asset_type: str | None) -> AssetClass:
    """Best-effort default classification when no metadata is registered.

    Uses ``asset_type`` as the primary signal so cryptocurrencies and US
    equities never collide with the BR ticker heuristics.
    """
    code = (asset_code or "").upper().strip()
    atype = (asset_type or "").lower().strip()

    if atype == "crypto":
        return "cripto"
    if atype in _INTERNATIONAL_ASSET_TYPES:
        return "stocks"
    if atype == "fii" or (len(code) >= 5 and code.endswith("11")):
        return "fii"
    if atype == "bdr" or (len(code) == 6 and code[-2:] in {"34", "35"}):
        return "bdr"
    if atype == "etf":
        return "etf"
    return "acao"


_SELECT_COLUMNS = (
    "asset_code, cnpj, asset_class, asset_name_oficial, source, notes, "
    "sector_category, sector_subcategory, site_ri, data_source, last_synced_at"
)


class AssetMetadataRepository:
    """Read/write helper for the ``asset_metadata`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, asset_code: str) -> AssetMetadata | None:
        row = self._conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
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
            SELECT {_SELECT_COLUMNS}
            FROM asset_metadata
            WHERE asset_code IN ({placeholders})
            """,
            codes,
        ).fetchall()
        return {str(row["asset_code"]): _row_to_metadata(row) for row in rows}

    def list_all(self) -> list[AssetMetadata]:
        rows = self._conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
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
        if metadata.asset_class not in _VALID_CLASSES:
            raise ValueError(
                f"Invalid asset_class={metadata.asset_class!r}; "
                f"must be one of {sorted(_VALID_CLASSES)}"
            )
        self._conn.execute(
            """
            INSERT INTO asset_metadata
                (asset_code, cnpj, asset_class, asset_name_oficial,
                 source, notes, sector_category, sector_subcategory,
                 site_ri, data_source, last_synced_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(asset_code) DO UPDATE SET
                cnpj                = excluded.cnpj,
                asset_class         = excluded.asset_class,
                asset_name_oficial  = excluded.asset_name_oficial,
                source              = excluded.source,
                notes               = excluded.notes,
                sector_category     = excluded.sector_category,
                sector_subcategory  = excluded.sector_subcategory,
                site_ri             = excluded.site_ri,
                data_source         = excluded.data_source,
                last_synced_at      = excluded.last_synced_at,
                updated_at          = excluded.updated_at
            """,
            (
                metadata.asset_code.upper(),
                metadata.cnpj,
                metadata.asset_class,
                metadata.asset_name_oficial,
                metadata.source,
                metadata.notes,
                metadata.sector_category,
                metadata.sector_subcategory,
                metadata.site_ri,
                metadata.data_source,
                metadata.last_synced_at,
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
    keys = set(row.keys())

    def _opt(name: str) -> str | None:
        if name not in keys:
            return None
        value = row[name]
        return value if value is not None else None

    return AssetMetadata(
        asset_code=str(row["asset_code"]),
        cnpj=_opt("cnpj"),
        asset_class=str(row["asset_class"]),  # type: ignore[arg-type]
        asset_name_oficial=_opt("asset_name_oficial"),
        source=str(row["source"]),
        notes=_opt("notes"),
        sector_category=_opt("sector_category"),
        sector_subcategory=_opt("sector_subcategory"),
        site_ri=_opt("site_ri"),
        data_source=_opt("data_source"),
        last_synced_at=_opt("last_synced_at"),
    )
