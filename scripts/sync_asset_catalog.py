"""Sync the ``asset_metadata`` table from the canonical asset catalog.

Reads ``data/asset_catalog/*.csv`` (via ``domain.asset_catalog.load_catalog``),
walks every distinct asset code present in operations + positions, and
upserts the master registry. Implements the universal "manual prevalece"
rule: never overwrites a non-NULL column on an existing row.

For tickers without a catalog entry, falls back to the heuristic
``infer_asset_class(asset_code, asset_type)`` so cryptocurrencies and
US equities get ``cripto`` / ``stocks`` instead of the legacy ``acao``
default.

Optional flags:

* ``--portfolio <id>``: scope discovery to a single portfolio.
* ``--dry-run``: print the plan without touching the DB.

Usage::

    uv run python scripts/sync_asset_catalog.py
    uv run python scripts/sync_asset_catalog.py --portfolio bruno__renda-variavel
    uv run python scripts/sync_asset_catalog.py --dry-run
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from domain.asset_catalog import CatalogEntry, load_catalog
from storage.repository.asset_metadata import (
    AssetMetadata,
    AssetMetadataRepository,
    infer_asset_class,
)
from storage.repository.db import Database


def _norm_cnpj(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())


def _collect_asset_codes(
    db: Database, *, portfolio_id: str | None
) -> dict[str, str | None]:
    """Return ``{asset_code: asset_type}`` from operations + positions."""
    conn = db.connection
    params: tuple[str, ...] = ()
    where = ""
    if portfolio_id:
        where = "WHERE portfolio_id = ?"
        params = (portfolio_id,)

    rows = conn.execute(
        f"""
        SELECT asset_code, asset_type FROM operations {where}
        UNION
        SELECT asset_code, asset_type FROM positions {where}
        """,
        params + params,
    ).fetchall()

    out: dict[str, str | None] = {}
    for row in rows:
        code = (row["asset_code"] or "").upper().strip()
        if not code or code == "BRL":
            continue
        atype = row["asset_type"]
        if code not in out or (out[code] is None and atype):
            out[code] = atype
    return out


def _build_payload_from_catalog(
    *,
    asset_code: str,
    asset_type: str | None,
    catalog: CatalogEntry | None,
    current: AssetMetadata | None,
    now_iso: str,
) -> AssetMetadata | None:
    """Build the ``AssetMetadata`` to upsert, applying "manual prevalece".

    Returns ``None`` when nothing changes (no insert, no fields to fill on
    an existing row).
    """
    if catalog is not None:
        inferred_class = catalog.asset_class
    else:
        inferred_class = infer_asset_class(asset_code, asset_type)

    if current is None:
        if catalog is not None:
            return AssetMetadata(
                asset_code=asset_code,
                cnpj=catalog.cnpj,
                asset_class=inferred_class,  # type: ignore[arg-type]
                asset_name_oficial=catalog.razao_social,
                source="catalog",
                notes=f"catalog: {catalog.fonte}" if catalog.fonte else None,
                sector_category=catalog.sector_category,
                sector_subcategory=catalog.sector_subcategory,
                site_ri=catalog.site_ri,
                data_source=f"catalog:{catalog.source_file}",
                last_synced_at=now_iso,
            )
        return AssetMetadata(
            asset_code=asset_code,
            cnpj=None,
            asset_class=inferred_class,  # type: ignore[arg-type]
            asset_name_oficial=None,
            source="auto",
            notes=None,
            sector_category=None,
            sector_subcategory=None,
            site_ri=None,
            data_source="auto",
            last_synced_at=now_iso,
        )

    # Existing row — manual prevalece. Só completa campos NULL com base no
    # catálogo (e jamais para asset_class, que pode ser uma reclassificação
    # manual deliberada).
    if catalog is None:
        return None

    new_cnpj = current.cnpj or catalog.cnpj
    new_name = current.asset_name_oficial or catalog.razao_social
    new_sector_cat = current.sector_category or catalog.sector_category
    new_sector_sub = current.sector_subcategory or catalog.sector_subcategory
    new_site_ri = current.site_ri or catalog.site_ri

    if (
        (new_cnpj == current.cnpj)
        and (new_name == current.asset_name_oficial)
        and (new_sector_cat == current.sector_category)
        and (new_sector_sub == current.sector_subcategory)
        and (new_site_ri == current.site_ri)
    ):
        return None

    return AssetMetadata(
        asset_code=asset_code,
        cnpj=new_cnpj,
        asset_class=current.asset_class,
        asset_name_oficial=new_name,
        source=current.source,
        notes=current.notes,
        sector_category=new_sector_cat,
        sector_subcategory=new_sector_sub,
        site_ri=new_site_ri,
        data_source=current.data_source or f"catalog:{catalog.source_file}",
        last_synced_at=now_iso,
    )


def run(*, db_path: Path, portfolio_id: str | None, dry_run: bool) -> None:
    catalog = load_catalog()
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with Database(db_path) as db:
        repo = AssetMetadataRepository(db.connection)
        existing = {m.asset_code: m for m in repo.list_all()}
        codes = _collect_asset_codes(db, portfolio_id=portfolio_id)

        to_upsert: list[AssetMetadata] = []
        catalog_divergences: list[str] = []
        class_counter: Counter[str] = Counter()
        new_count = 0

        # Cobertura completa: tickers do ledger + tickers só presentes no
        # catálogo (úteis para preencher stale data antes do primeiro import).
        all_tickers = sorted(set(codes) | set(catalog))

        for code in all_tickers:
            asset_type = codes.get(code)
            entry = catalog.get(code)
            current = existing.get(code)

            payload = _build_payload_from_catalog(
                asset_code=code,
                asset_type=asset_type,
                catalog=entry,
                current=current,
                now_iso=now_iso,
            )

            if entry is not None and current is not None:
                if (
                    current.cnpj
                    and entry.cnpj
                    and _norm_cnpj(current.cnpj) != _norm_cnpj(entry.cnpj)
                ):
                    catalog_divergences.append(
                        f"  {code:<8} CNPJ: banco={current.cnpj!r} "
                        f"catalog={entry.cnpj!r}"
                    )
                if (
                    current.asset_name_oficial
                    and entry.razao_social
                    and current.asset_name_oficial.strip().upper()
                    != entry.razao_social.strip().upper()
                ):
                    catalog_divergences.append(
                        f"  {code:<8} nome: banco={current.asset_name_oficial!r} "
                        f"catalog={entry.razao_social!r}"
                    )

            if payload is None:
                continue

            if current is None:
                new_count += 1
                class_counter[payload.asset_class] += 1
            to_upsert.append(payload)

        print(f"Tickers analisados: {len(all_tickers)}")
        print(f"  do ledger      : {len(codes)}")
        print(f"  do catálogo    : {len(catalog)}")
        print(f"  já cadastrados : {len(existing)}")
        print(f"  a inserir      : {new_count}")
        print(f"  a atualizar    : {len(to_upsert) - new_count}")

        if catalog_divergences:
            print(
                "\n⚠️  DIVERGÊNCIAS detectadas entre catálogo e banco "
                "(dado manual prevalece — revise as diferenças):"
            )
            for line in catalog_divergences:
                print(line)

        if class_counter:
            print("\nDistribuição de novos cadastros:", dict(class_counter))

        if dry_run:
            print("\n[dry-run] Nada foi escrito no banco.")
            return

        for meta in to_upsert:
            repo.upsert(meta, commit=False)
        db.connection.commit()

        if to_upsert:
            print(
                f"\nOK. {len(to_upsert)} linha(s) gravada(s). "
                f"Edite a classe IRPF de FIAGROs ou rode a skill "
                f"`asset-metadata-enrich` para preencher os CNPJs faltantes."
            )
        else:
            print("\nNada a fazer — banco já está sincronizado com o catálogo.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync asset_metadata from data/asset_catalog/*.csv and the operations ledger."
        )
    )
    parser.add_argument("--db", default="ia_invest.db", help="SQLite DB path")
    parser.add_argument(
        "--portfolio",
        default=None,
        help="Restrict discovery to a single portfolio_id (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without writing to the DB",
    )
    args = parser.parse_args()

    run(
        db_path=Path(args.db),
        portfolio_id=args.portfolio,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
