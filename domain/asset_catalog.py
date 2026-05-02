"""Cross-domain loader for the asset catalog (``data/asset_catalog/*.csv``).

The catalog is the canonical, version-controlled source of truth for asset
identification (CNPJ, official name, IRPF classification, sector hints,
official RI URL). It is consumed by:

* ``scripts/sync_asset_catalog.py`` — populates the ``asset_metadata`` SQLite
  table after ``make reset-db`` / ``make import-all``.
* ``domain.irpf.builder`` — falls back to catalog values when the DB row is
  missing some field.
* ``scripts/dump_asset_metadata_seed.py`` — promotes DB rows back into the
  catalog files.

Files are split by ``asset_class`` to keep PR diffs focused; the loader
aggregates them into a single ``{ticker: CatalogEntry}`` dict and validates
class consistency + ticker uniqueness across all files.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "asset_catalog"

_VALID_CLASSES = frozenset(
    {"acao", "fii", "fiagro", "bdr", "etf", "cripto", "stocks"}
)

# Mapping arquivo → conjunto de classes esperadas dentro dele.
_FILE_TO_CLASSES: dict[str, frozenset[str]] = {
    "acoes.csv": frozenset({"acao"}),
    "fiis.csv": frozenset({"fii", "fiagro"}),
    "criptos.csv": frozenset({"cripto"}),
    "stocks.csv": frozenset({"stocks"}),
    "bdrs.csv": frozenset({"bdr"}),
    "etfs.csv": frozenset({"etf"}),
}


@dataclass(frozen=True)
class CatalogEntry:
    ticker: str
    cnpj: str | None
    razao_social: str | None
    asset_class: str
    sector_category: str | None
    sector_subcategory: str | None
    site_ri: str | None
    fonte: str | None
    source_file: str


def _read_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        cleaned_lines = [
            line for line in fh
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if not cleaned_lines:
        return []
    return list(csv.DictReader(cleaned_lines))


def load_catalog(directory: Path | None = None) -> dict[str, CatalogEntry]:
    """Read every catalog CSV under ``directory`` and aggregate by ticker.

    Raises ``ValueError`` on duplicate tickers (across files), invalid
    ``asset_class`` values, or class/file mismatches. Empty/missing files
    are silently ignored.
    """
    base = directory or CATALOG_DIR
    if not base.exists():
        return {}

    out: dict[str, CatalogEntry] = {}
    for csv_path in sorted(base.glob("*.csv")):
        expected_classes = _FILE_TO_CLASSES.get(csv_path.name)
        for row_num, row in enumerate(_read_csv(csv_path), start=2):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            cls = (row.get("asset_class") or "").strip().lower()
            if cls not in _VALID_CLASSES:
                raise ValueError(
                    f"{csv_path.name}: linha {row_num} ({ticker}) tem classe "
                    f"inválida {cls!r}; permitido: {sorted(_VALID_CLASSES)}"
                )
            if expected_classes is not None and cls not in expected_classes:
                raise ValueError(
                    f"{csv_path.name}: linha {row_num} ({ticker}) tem classe "
                    f"{cls!r} mas o arquivo só aceita {sorted(expected_classes)}"
                )
            if ticker in out:
                raise ValueError(
                    f"{csv_path.name}: ticker duplicado {ticker!r} "
                    f"(linha {row_num}); já presente em {out[ticker].source_file}"
                )

            out[ticker] = CatalogEntry(
                ticker=ticker,
                cnpj=_norm(row.get("cnpj")),
                razao_social=_norm(row.get("razao_social")),
                asset_class=cls,
                sector_category=_norm(row.get("sector_category")),
                sector_subcategory=_norm(row.get("sector_subcategory")),
                site_ri=_norm(row.get("site_ri")),
                fonte=_norm(row.get("fonte")),
                source_file=csv_path.name,
            )

    return out


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
