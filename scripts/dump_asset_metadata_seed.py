"""Dump curated asset_metadata rows back into the versioned catalog CSVs.

The catalog (`data/asset_catalog/{acoes,fiis,criptos,stocks,bdrs,etfs}.csv`)
is the canonical, version-controlled source of truth. Whenever you fill in
missing CNPJ/razão social/sector via the UI, the `asset-metadata-enrich`
skill or ad-hoc edits, run this script to push those rows back into the
right CSV file so they survive the next `make reset-db`.

Behaviour:

* Reads every row from ``asset_metadata`` (DB).
* Keeps only rows that have BOTH ``cnpj`` and ``asset_name_oficial`` filled
  (rows still missing the basics are not promoted).
  Exception: rows with ``asset_class in {cripto, stocks}`` are kept
  even without CNPJ (it doesn't apply to those classes).
* Skips rows where ``source = 'auto'`` (those were created by the bootstrap
  inferring a class without human confirmation).
* Splits rows across the catalog files by ``asset_class``:

    acao             → data/asset_catalog/acoes.csv
    fii / fiagro     → data/asset_catalog/fiis.csv
    cripto           → data/asset_catalog/criptos.csv
    stocks           → data/asset_catalog/stocks.csv
    bdr              → data/asset_catalog/bdrs.csv (created on demand)
    etf              → data/asset_catalog/etfs.csv (created on demand)

* Preserves the comment header (everything up to and including the
  ``ticker,...`` header line) of each existing catalog file.
* Writes rows alphabetically by ticker.

Usage::

    uv run python scripts/dump_asset_metadata_seed.py            # dry-run
    uv run python scripts/dump_asset_metadata_seed.py --write    # overwrite
    uv run python scripts/dump_asset_metadata_seed.py --db /path/to/other.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from domain.asset_catalog import CATALOG_DIR, CatalogEntry, load_catalog
from storage.repository.asset_metadata import (
    AssetMetadata,
    AssetMetadataRepository,
)
from storage.repository.db import Database

_HEADER_LINE = (
    "ticker,cnpj,razao_social,asset_class,sector_category,"
    "sector_subcategory,site_ri,fonte"
)

# Mapping (asset_class no DB) → (arquivo de destino no catálogo).
_CLASS_TO_FILE: dict[str, str] = {
    "acao": "acoes.csv",
    "fii": "fiis.csv",
    "fiagro": "fiis.csv",
    "cripto": "criptos.csv",
    "stocks": "stocks.csv",
    "bdr": "bdrs.csv",
    "etf": "etfs.csv",
}


def _read_header_block(path: Path, default: list[str]) -> list[str]:
    """Return all lines up to and including the CSV header, or ``default``."""
    if not path.exists():
        return default
    block: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            block.append(line)
            if line.strip() == _HEADER_LINE:
                return block
    raise ValueError(
        f"Catalog file {path} does not contain header line "
        f"'{_HEADER_LINE}'. Aborting to avoid clobbering custom format."
    )


def _default_header(filename: str) -> list[str]:
    return [
        f"# Catálogo de ativos — {filename}\n",
        "# Schema canônico: ver data/asset_catalog/README.md.\n",
        f"{_HEADER_LINE}\n",
    ]


def _strip_catalog_prefix(notes: str | None) -> str:
    if not notes:
        return ""
    if notes.startswith("catalog:"):
        return notes[len("catalog:"):].strip()
    if notes.startswith("seed:"):
        return notes[len("seed:"):].strip()
    return notes.strip()


def _csv_escape(value: str | None) -> str:
    text = value or ""
    if any(c in text for c in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _is_eligible(row: AssetMetadata) -> bool:
    if (row.source or "").lower() == "auto":
        return False
    if not row.asset_name_oficial:
        return False
    if row.asset_class in {"cripto", "stocks"}:
        # Não exigimos CNPJ para essas classes.
        return True
    return bool(row.cnpj)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump asset_metadata rows back into the versioned catalog CSVs."
    )
    parser.add_argument(
        "--db",
        default="ia_invest.db",
        help="Path to the SQLite database (default: ia_invest.db).",
    )
    parser.add_argument(
        "--catalog-dir",
        default=str(CATALOG_DIR),
        help=f"Path to the catalog directory (default: {CATALOG_DIR}).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Overwrite the catalog files. Without this flag the script only "
             "prints a diff summary (dry-run).",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        return 1

    catalog_dir = Path(args.catalog_dir)

    with Database(db_path) as db:
        repo = AssetMetadataRepository(db.connection)
        all_rows = repo.list_all()

    eligible = sorted(
        (row for row in all_rows if _is_eligible(row)),
        key=lambda r: r.asset_code,
    )
    skipped_class: dict[str, int] = {}
    for row in all_rows:
        if not _is_eligible(row):
            skipped_class[row.asset_class] = (
                skipped_class.get(row.asset_class, 0) + 1
            )

    # Quebra rows por arquivo destino.
    by_file: dict[str, list[AssetMetadata]] = {}
    unsupported: list[AssetMetadata] = []
    for row in eligible:
        target = _CLASS_TO_FILE.get(row.asset_class)
        if target is None:
            unsupported.append(row)
            continue
        by_file.setdefault(target, []).append(row)

    existing_catalog: dict[str, CatalogEntry] = (
        load_catalog(catalog_dir) if catalog_dir.exists() else {}
    )

    print(f"DB rows total:        {len(all_rows)}")
    print(f"Elegíveis para CSV:   {len(eligible)}")
    print(f"Catálogo atual:       {len(existing_catalog)} tickers em "
          f"{catalog_dir}")
    if skipped_class:
        print(f"Ignoradas (auto/sem dados): {skipped_class}")
    if unsupported:
        print(f"Sem mapeamento de arquivo: {[r.asset_code for r in unsupported]}")

    for filename in sorted(by_file):
        rows = by_file[filename]
        new_tickers = [
            r.asset_code for r in rows if r.asset_code not in existing_catalog
        ]
        print(
            f"\n  {filename}: {len(rows)} linha(s) elegível(is); "
            f"{len(new_tickers)} novo(s) em relação ao CSV atual."
        )
        if new_tickers:
            print(f"      novos: {', '.join(new_tickers)}")

    if not args.write:
        print("\n(dry-run — passe --write para sobrescrever os CSVs do catálogo)")
        return 0

    catalog_dir.mkdir(parents=True, exist_ok=True)

    for filename, rows in sorted(by_file.items()):
        target_path = catalog_dir / filename
        # Merge com o que já está no arquivo: dado já presente é preservado
        # (o catálogo nunca apaga linhas que estavam só nele).
        merged: dict[str, dict[str, str]] = {}
        if target_path.exists():
            for ticker, entry in existing_catalog.items():
                if entry.source_file != filename:
                    continue
                merged[ticker] = {
                    "ticker": ticker,
                    "cnpj": entry.cnpj or "",
                    "razao_social": entry.razao_social or "",
                    "asset_class": entry.asset_class,
                    "sector_category": entry.sector_category or "",
                    "sector_subcategory": entry.sector_subcategory or "",
                    "site_ri": entry.site_ri or "",
                    "fonte": entry.fonte or "",
                }
        for row in rows:
            prev = merged.get(row.asset_code, {})
            fonte = (
                _strip_catalog_prefix(row.notes)
                or prev.get("fonte")
                or "DB dump"
            )
            merged[row.asset_code] = {
                "ticker": row.asset_code,
                "cnpj": row.cnpj or "",
                "razao_social": row.asset_name_oficial or "",
                "asset_class": row.asset_class,
                "sector_category": row.sector_category or "",
                "sector_subcategory": row.sector_subcategory or "",
                "site_ri": row.site_ri or "",
                "fonte": fonte,
            }

        header_block = _read_header_block(target_path, _default_header(filename))
        with target_path.open("w", encoding="utf-8") as fh:
            for line in header_block:
                fh.write(line)
            for ticker in sorted(merged):
                row = merged[ticker]
                fields = [
                    _csv_escape(row.get("ticker")),
                    _csv_escape(row.get("cnpj")),
                    _csv_escape(row.get("razao_social")),
                    _csv_escape(row.get("asset_class")),
                    _csv_escape(row.get("sector_category")),
                    _csv_escape(row.get("sector_subcategory")),
                    _csv_escape(row.get("site_ri")),
                    _csv_escape(row.get("fonte")),
                ]
                fh.write(",".join(fields) + "\n")

        print(f"  → {target_path}: {len(merged)} linha(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
