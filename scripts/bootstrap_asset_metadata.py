"""Bootstrap the ``asset_metadata`` table from the operations ledger.

For every distinct asset code present in operations and/or positions that
does not yet have a row in ``asset_metadata``, insert one with the inferred
IRPF class (``acao`` / ``fii`` / ``bdr`` / ``etf``). CNPJ and official name
are left ``NULL`` for the user to fill in later.

This eliminates the ``asset_metadata_missing`` warning in the Simulador IR
and turns the remaining alerts into per-row ``cnpj_missing`` reminders.

Optional flags:

* ``--portfolio <id>``: scope the discovery to a single portfolio.
* ``--reclassify``: also overwrite the class of existing rows whose
  ``source = 'auto'`` when the inference disagrees (manual edits with any
  other ``source`` are always preserved).
* ``--dry-run``: print what would change without touching the DB.

Usage::

    uv run python scripts/bootstrap_asset_metadata.py
    uv run python scripts/bootstrap_asset_metadata.py --portfolio default__rv
    uv run python scripts/bootstrap_asset_metadata.py --dry-run
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from domain.irpf.seed import load_seed
from storage.repository.asset_metadata import (
    AssetMetadata,
    AssetMetadataRepository,
    infer_asset_class_irpf,
)
from storage.repository.db import Database


def _norm_cnpj(value: str | None) -> str:
    """Mantém apenas os dígitos do CNPJ (para comparação)."""
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
        # Mantém o primeiro asset_type não vazio que aparecer.
        if code not in out or (out[code] is None and atype):
            out[code] = atype
    return out


def run(*, db_path: Path, portfolio_id: str | None, dry_run: bool, reclassify: bool) -> None:
    seed = load_seed()
    with Database(db_path) as db:
        repo = AssetMetadataRepository(db.connection)
        existing = {m.asset_code: m for m in repo.list_all()}
        codes = _collect_asset_codes(db, portfolio_id=portfolio_id)

        to_insert: list[AssetMetadata] = []
        to_update: list[AssetMetadata] = []
        seed_divergences: list[str] = []
        class_counter: Counter[str] = Counter()

        for code, asset_type in sorted(codes.items()):
            seed_entry = seed.get(code)
            inferred_class = (
                seed_entry.asset_class_irpf
                if seed_entry is not None
                else infer_asset_class_irpf(code, asset_type)
            )
            current = existing.get(code)

            if current is None:
                to_insert.append(
                    AssetMetadata(
                        asset_code=code,
                        cnpj=seed_entry.cnpj if seed_entry else None,
                        asset_class_irpf=inferred_class,
                        asset_name_oficial=(
                            seed_entry.razao_social if seed_entry else None
                        ),
                        source="seed" if seed_entry else "auto",
                        notes=(
                            f"seed: {seed_entry.fonte}"
                            if seed_entry and seed_entry.fonte
                            else None
                        ),
                    )
                )
                class_counter[inferred_class] += 1
                continue

            # Linha já existe. Preenche apenas campos NULL a partir do seed,
            # nunca sobrescreve dado manual já presente.
            if seed_entry is not None:
                needs_cnpj = current.cnpj is None and seed_entry.cnpj
                needs_name = current.asset_name_oficial is None and seed_entry.razao_social
                # Divergências: dado já preenchido manualmente difere do seed.
                if current.cnpj and seed_entry.cnpj and _norm_cnpj(current.cnpj) != _norm_cnpj(seed_entry.cnpj):
                    seed_divergences.append(
                        f"  {code:<8} CNPJ: banco={current.cnpj!r} seed={seed_entry.cnpj!r}"
                    )
                if (
                    current.asset_name_oficial
                    and seed_entry.razao_social
                    and current.asset_name_oficial.strip().upper()
                    != seed_entry.razao_social.strip().upper()
                ):
                    seed_divergences.append(
                        f"  {code:<8} nome: banco={current.asset_name_oficial!r} "
                        f"seed={seed_entry.razao_social!r}"
                    )

                if needs_cnpj or needs_name:
                    to_update.append(
                        AssetMetadata(
                            asset_code=code,
                            cnpj=current.cnpj or seed_entry.cnpj or None,
                            asset_class_irpf=current.asset_class_irpf,
                            asset_name_oficial=(
                                current.asset_name_oficial
                                or seed_entry.razao_social
                                or None
                            ),
                            source=current.source,
                            notes=current.notes,
                        )
                    )
                    continue

            if (
                reclassify
                and current.source == "auto"
                and current.asset_class_irpf != inferred_class
            ):
                to_update.append(
                    AssetMetadata(
                        asset_code=code,
                        cnpj=current.cnpj,
                        asset_class_irpf=inferred_class,
                        asset_name_oficial=current.asset_name_oficial,
                        source="auto",
                        notes=current.notes,
                    )
                )

        print(f"Tickers analisados: {len(codes)}")
        print(f"  já cadastrados : {len(codes) - len(to_insert)}")
        print(f"  a inserir      : {len(to_insert)}")
        print(f"  do seed CSV    : {sum(1 for m in to_insert if m.source == 'seed')}")
        if reclassify or to_update:
            print(f"  a atualizar    : {len(to_update)}")

        if seed_divergences:
            print(
                "\n⚠️  DIVERGÊNCIAS detectadas entre seed CSV e banco "
                "(dado manual prevalece, revise as diferenças):"
            )
            for line in seed_divergences:
                print(line)

        if to_insert:
            print("\nNovos cadastros (classe IRPF inferida):")
            for meta in to_insert:
                print(f"  {meta.asset_code:<8} -> {meta.asset_class_irpf}")
            print("\nDistribuição:", dict(class_counter))

        if to_update:
            print("\nReclassificações pendentes:")
            for meta in to_update:
                print(f"  {meta.asset_code:<8} -> {meta.asset_class_irpf}")

        if dry_run:
            print("\n[dry-run] Nada foi escrito no banco.")
            return

        for meta in to_insert + to_update:
            repo.upsert(meta, commit=False)
        db.connection.commit()

        if to_insert or to_update:
            print(
                "\nOK. Edite a classe IRPF de FIAGROs (ex.: BTAL11, BTRA11, GALG11) "
                "e preencha os CNPJs via o painel ou via UPDATE direto na tabela "
                "asset_metadata para sumir com os alertas restantes."
            )
        else:
            print("\nNada a fazer — todos os tickers já estão cadastrados.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap asset_metadata classifying every ticker found in operations/positions."
        )
    )
    parser.add_argument("--db", default="ia_invest.db", help="SQLite DB path")
    parser.add_argument(
        "--portfolio",
        default=None,
        help="Restrict discovery to a single portfolio_id (default: all)",
    )
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="Overwrite the class of existing rows with source='auto' when inference differs",
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
        reclassify=args.reclassify,
    )


if __name__ == "__main__":
    main()
