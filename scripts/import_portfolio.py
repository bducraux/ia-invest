"""Import files for a single portfolio.

Scans portfolios/<portfolio-id>/inbox/ for files, runs the appropriate
extractor + normalizer, persists operations in SQLite and moves files to
processed/ or rejected/.

Usage::

    python scripts/import_portfolio.py --portfolio renda-variavel
    python scripts/import_portfolio.py --portfolio cripto --db path/to/ia_invest.db
    python scripts/import_portfolio.py --portfolio renda-variavel --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

import structlog

from domain.deduplication import DeduplicationService
from domain.models import ImportJob
from domain.portfolio_service import PortfolioService
from domain.position_service import PositionService
from domain.previdencia import PrevidenciaSnapshot
from extractors import get_extractor, list_source_types
from extractors.avenue_apex_pdf import AvenueApexPdfExtractor
from extractors.cache import load_cached_extraction, save_cached_extraction
from extractors.previdencia_ibm_pdf import PrevidenciaIbmPdfExtractor
from mcp_server.services.fx_rates import FxRateService
from normalizers.fixed_income_csv import REQUIRED_COLUMNS as FIXED_INCOME_REQUIRED_COLUMNS
from normalizers.fixed_income_csv import FixedIncomeCSVImporter
from normalizers.operations import OperationNormalizer
from storage.repository.avenue_aliases import AvenueAliasesRepository
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.fx_rates import FxRatesRepository
from storage.repository.import_jobs import ImportJobRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger()

_PORTFOLIOS_DIR = Path("portfolios")
_SPECIAL_SOURCE_TYPES = {"fixed_income_csv", "previdencia_ibm_pdf"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_extractor_for_file(
    file_path: Path,
    enabled_sources: list[str],
    *,
    portfolio_id: str | None = None,
    alias_repo: AvenueAliasesRepository | None = None,
) -> Any | None:
    """Find the first enabled extractor that can handle the file."""
    for source_type in enabled_sources:
        if source_type in _SPECIAL_SOURCE_TYPES:
            continue
        try:
            if source_type == "avenue_apex_pdf":
                extractor: Any = AvenueApexPdfExtractor(
                    alias_repo=alias_repo,
                    portfolio_id=portfolio_id,
                )
            else:
                extractor = get_extractor(source_type)
            if extractor.can_handle(file_path):
                return extractor
        except KeyError:
            log.warning("unknown_source_type", source_type=source_type)
    return None


def _read_text_with_fallback(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _is_fixed_income_csv(file_path: Path) -> bool:
    if file_path.suffix.lower() not in {".csv", ".txt"}:
        return False

    try:
        text = _read_text_with_fallback(file_path)
    except OSError:
        return False

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(text.splitlines(), dialect=dialect)
    try:
        header = next(reader)
    except StopIteration:
        return False

    normalized_header = {column.strip().lower() for column in header if column}
    return all(column in normalized_header for column in FIXED_INCOME_REQUIRED_COLUMNS)


def _select_latest_previdencia_file(files: list[Path], enabled_sources: list[str]) -> Path | None:
    if "previdencia_ibm_pdf" not in enabled_sources:
        return None

    extractor = get_extractor("previdencia_ibm_pdf")
    if not isinstance(extractor, PrevidenciaIbmPdfExtractor):
        return None

    latest: tuple[Path, str] | None = None
    for file_path in files:
        if not extractor.can_handle(file_path):
            continue
        try:
            period_month = extractor.extract_period_month(file_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("skip_previdencia_file", path=str(file_path), error=str(exc))
            continue

        if latest is None or period_month > latest[1]:
            latest = (file_path, period_month)

    return latest[0] if latest is not None else None


def _import_fixed_income_file(
    *,
    portfolio_id: str,
    staged_path: Path,
    dry_run: bool,
    job_id: int | None,
    job_repo: ImportJobRepository,
    fi_repo: FixedIncomePositionRepository,
) -> dict[str, int]:
    text = _read_text_with_fallback(staged_path)
    result = FixedIncomeCSVImporter().parse_text(text, portfolio_id=portfolio_id)

    for position in result.valid:
        position.import_job_id = job_id

    for err in result.errors:
        log.warning(
            "normalization_error",
            file=staged_path.name,
            row=err.row_index,
            error=err.message,
        )
        if not dry_run and job_id:
            job_repo.log_error(
                job_id,
                error_type="validation",
                message=err.message,
                row_index=err.row_index,
                field=err.field,
                raw_data=err.raw,
            )

    inserted = 0
    if not dry_run and result.valid:
        inserted = fi_repo.insert_many(result.valid)

    return {
        "total": result.total,
        "inserted": inserted,
        "skipped": 0,
        "errors": len(result.errors),
    }


def _import_previdencia_ibm_file(
    *,
    portfolio_id: str,
    staged_path: Path,
    dry_run: bool,
    job_id: int | None,
    job_repo: ImportJobRepository,
    prev_repo: PrevidenciaSnapshotRepository,
    extractor: PrevidenciaIbmPdfExtractor,
) -> dict[str, int]:
    extraction = extractor.extract(staged_path)
    for err in extraction.errors:
        log.warning(
            "extraction_error",
            file=staged_path.name,
            error=err.get("message"),
        )
        if not dry_run and job_id:
            job_repo.log_error(
                job_id,
                error_type=err.get("error_type", "parsing"),
                message=err.get("message", ""),
                row_index=err.get("row_index"),
                raw_data=err.get("raw_data"),
            )

    inserted = 0
    skipped = 0
    if not dry_run:
        for record in extraction.records:
            snapshot = PrevidenciaSnapshot(
                portfolio_id=portfolio_id,
                asset_code=str(record["asset_code"]),
                product_name=str(record["product_name"]),
                quantity=float(record["quantity"]),
                unit_price_cents=int(record["unit_price_cents"]),
                market_value_cents=int(record["market_value_cents"]),
                period_month=str(record["period_month"]),
                period_start_date=(
                    str(record["period_start_date"])
                    if record.get("period_start_date") is not None
                    else None
                ),
                period_end_date=(
                    str(record["period_end_date"])
                    if record.get("period_end_date") is not None
                    else None
                ),
                source_file=staged_path.name,
                import_job_id=job_id,
            )
            status = prev_repo.upsert_if_newer(snapshot)
            if status == "skipped_older":
                skipped += 1
                if job_id:
                    job_repo.log_error(
                        job_id,
                        error_type="deduplication",
                        message=(
                            "Snapshot skipped because statement month is older than current state"
                        ),
                        raw_data=record,
                    )
            else:
                inserted += 1

    return {
        "total": extraction.total,
        "inserted": inserted,
        "skipped": skipped,
        "errors": len(extraction.errors),
    }


def _find_portfolio_dir(portfolio_id: str, *, owner_id: str | None = None) -> Path | None:
    """Locate a portfolio directory under either the new
    ``portfolios/<owner>/<portfolio>/`` layout or the legacy
    ``portfolios/<portfolio>/`` layout.  When ``owner_id`` is provided, only
    that owner's subtree is considered.

    ``portfolio_id`` may be either:
      * a raw slug (e.g. ``renda-fixa``), or
      * a namespaced id (e.g. ``bruno__renda-fixa``) which encodes the owner
        directly and bypasses the cross-owner ambiguity check.
    """
    # Namespaced id takes precedence over the optional owner_id arg.
    if "__" in portfolio_id:
        ns_owner, slug = portfolio_id.split("__", 1)
        if owner_id and owner_id != ns_owner:
            return None
        candidate = _PORTFOLIOS_DIR / ns_owner / slug
        return candidate if candidate.exists() else None

    if owner_id:
        candidate = _PORTFOLIOS_DIR / owner_id / portfolio_id
        return candidate if candidate.exists() else None

    # 1) New layout — search every owner directory for a matching portfolio.
    #    If multiple owners have a portfolio with the same slug we refuse to
    #    pick one silently; the caller must disambiguate via --owner or by
    #    using the namespaced id.
    matches: list[Path] = []
    if _PORTFOLIOS_DIR.exists():
        for owner_dir in _PORTFOLIOS_DIR.iterdir():
            if not owner_dir.is_dir():
                continue
            candidate = owner_dir / portfolio_id
            if (candidate / "portfolio.yml").exists():
                matches.append(candidate)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        owners = sorted(m.parent.name for m in matches)
        raise ValueError(
            f"Portfolio slug '{portfolio_id}' is ambiguous across owners "
            f"({', '.join(owners)}). Use --owner <id> or pass the namespaced "
            f"id (e.g. '{owners[0]}__{portfolio_id}')."
        )

    # 2) Legacy single-level layout — kept for backward compatibility with
    #    older fixtures and tests.
    legacy = _PORTFOLIOS_DIR / portfolio_id
    if (legacy / "portfolio.yml").exists():
        return legacy
    return None


def import_portfolio(
    portfolio_id: str,
    *,
    db_path: Path = Path("ia_invest.db"),
    dry_run: bool = False,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Import all inbox files for the given portfolio.

    Returns a summary dict with counts and status.

    The portfolio is located under either the new
    ``portfolios/<owner>/<portfolio>/`` layout (preferred) or the legacy
    ``portfolios/<portfolio>/`` layout.  When the new layout is used and the
    ``portfolio.yml`` ``owner_id`` does not match the parent folder name,
    the import is aborted with an explicit error.
    """
    portfolio_dir = _find_portfolio_dir(portfolio_id, owner_id=owner_id)
    if portfolio_dir is None:
        searched = (
            f"portfolios/{owner_id}/{portfolio_id}"
            if owner_id
            else f"portfolios/<owner>/{portfolio_id} or portfolios/{portfolio_id}"
        )
        log.error("portfolio_dir_not_found", portfolio=portfolio_id, searched=searched)
        return {"error": f"Portfolio directory not found: {searched}"}

    manifest_path = portfolio_dir / "portfolio.yml"

    # Load and validate portfolio manifest
    portfolio_svc = PortfolioService()
    try:
        portfolio = portfolio_svc.load_from_yaml(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        log.error("manifest_error", error=str(exc))
        return {"error": str(exc)}

    # New layout: validate that portfolio.yml::owner_id matches the parent
    # folder name.  When the portfolio lives directly under portfolios/ (legacy
    # single-level layout) the parent folder is `portfolios` and we skip the
    # check for backward compatibility.
    parent_dir_name = portfolio_dir.parent.name
    if parent_dir_name != _PORTFOLIOS_DIR.name and parent_dir_name != portfolio.owner_id:
        message = (
            f"Owner mismatch for portfolio '{portfolio_id}': "
            f"folder is owned by '{parent_dir_name}' but portfolio.yml "
            f"declares owner_id='{portfolio.owner_id}'. "
            "Either rename the parent folder or update the manifest."
        )
        log.error(
            "owner_id_mismatch",
            portfolio=portfolio_id,
            folder_owner=parent_dir_name,
            manifest_owner=portfolio.owner_id,
        )
        return {"error": message}

    # The local CLI argument `portfolio_id` may be a slug (e.g. "renda-fixa")
    # but the canonical database id is owner-scoped (e.g. "bruno__renda-fixa").
    # Reassign so every downstream call (repositories, FKs, log entries) uses
    # the namespaced id consistently.
    portfolio_slug = portfolio.slug
    portfolio_id = portfolio.id

    inbox = portfolio_dir / "inbox"
    staging = portfolio_dir / "staging"
    processed = portfolio_dir / "processed"
    rejected = portfolio_dir / "rejected"

    for d in (inbox, staging, processed, rejected):
        d.mkdir(parents=True, exist_ok=True)

    # Gather files to process
    files = [f for f in inbox.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        log.info("no_files_in_inbox", portfolio=portfolio_id)
        return {"portfolio": portfolio_id, "files_processed": 0}

    # Resolve enabled source types from manifest
    enabled_sources: list[str] = []
    if portfolio.config:
        for src in portfolio.config.get("sources", []):
            if src.get("enabled", False):
                enabled_sources.append(src["type"])
    if not enabled_sources:
        enabled_sources = list_source_types()

    with Database(db_path) as db:
        db.initialize()

        # Ensure the owner member exists (auto-upsert from manifest data).
        # This keeps the import lenient: users who provision portfolio
        # folders manually don't need to also run `create_member.py` first.
        from domain.members import Member  # local import to avoid cycles
        from storage.repository.members import MemberRepository

        member_repo = MemberRepository(db.connection)
        if member_repo.get(portfolio.owner_id) is None:
            log.info(
                "auto_creating_owner_member",
                owner_id=portfolio.owner_id,
                portfolio=portfolio_id,
            )
            member_repo.upsert(
                Member(id=portfolio.owner_id, name=portfolio.owner_id)
            )

        # Ensure portfolio is registered in DB
        portfolio_repo = PortfolioRepository(db.connection)
        portfolio_repo.upsert(portfolio)

        op_repo = OperationRepository(db.connection)
        pos_repo = PositionRepository(db.connection)
        fi_repo = FixedIncomePositionRepository(db.connection)
        prev_repo = PrevidenciaSnapshotRepository(db.connection)
        job_repo = ImportJobRepository(db.connection)
        fx_repo = FxRatesRepository(db.connection)
        fx_service = FxRateService(fx_repo)
        alias_repo = AvenueAliasesRepository(db.connection)
        normalizer = OperationNormalizer(fx_service=fx_service)
        dedup_svc = DeduplicationService()
        pos_svc = PositionService()

        summary: dict[str, Any] = {
            "portfolio": portfolio_id,
            "files_processed": 0,
            "files_rejected": 0,
            "total_records": 0,
            "inserted": 0,
            "skipped": 0,
            "errors": 0,
        }

        latest_previdencia_file: Path | None = None
        if portfolio_slug == "fundacao-ibm":
            latest_previdencia_file = _select_latest_previdencia_file(files, enabled_sources)

        # Pre-pass: harvest Avenue/Apex aliases (description → ticker) from
        # ALL Apex PDFs before the main import so chronologically-early
        # statements without a PORTFOLIO SUMMARY (e.g. cash-only months)
        # can still resolve their BOUGHT lines via the cache.
        if "avenue_apex_pdf" in enabled_sources:
            from extractors.cache import file_sha256, load_cached_aliases

            harvest_extractor = AvenueApexPdfExtractor(
                alias_repo=alias_repo, portfolio_id=portfolio_id
            )
            for file_path in files:
                if file_path.suffix.lower() != ".pdf":
                    continue
                try:
                    pdf_hash = file_sha256(file_path)
                    cached_aliases = load_cached_aliases(
                        file_path, harvest_extractor, file_hash=pdf_hash
                    )
                    if cached_aliases is not None:
                        # Cache hit: replay aliases without opening the PDF.
                        for entry in cached_aliases:
                            name = entry.get("name")
                            symbol = entry.get("symbol")
                            if not name or not symbol:
                                continue
                            alias_repo.upsert(
                                portfolio_id,
                                name,
                                symbol,
                                cusip=entry.get("cusip"),
                                commit=False,
                            )
                        continue
                    if harvest_extractor.can_handle(file_path):
                        harvest_extractor.harvest_aliases(
                            file_path, file_hash=pdf_hash
                        )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "alias_harvest_failed",
                        file=file_path.name,
                        error=str(exc),
                    )
            if not dry_run:
                db.connection.commit()

        for file_path in sorted(files):
            log.info("processing_file", file=file_path.name, portfolio=portfolio_id)

            is_fixed_income_file = (
                "fixed_income_csv" in enabled_sources and _is_fixed_income_csv(file_path)
            )
            is_previdencia_file = False
            previdencia_extractor: PrevidenciaIbmPdfExtractor | None = None
            if "previdencia_ibm_pdf" in enabled_sources:
                maybe_prev_extractor = get_extractor("previdencia_ibm_pdf")
                if isinstance(maybe_prev_extractor, PrevidenciaIbmPdfExtractor):
                    previdencia_extractor = maybe_prev_extractor
                    is_previdencia_file = previdencia_extractor.can_handle(file_path)

            extractor = None if (is_fixed_income_file or is_previdencia_file) else _find_extractor_for_file(
                file_path,
                enabled_sources,
                portfolio_id=portfolio_id,
                alias_repo=alias_repo,
            )
            if extractor is None and not is_fixed_income_file and not is_previdencia_file:
                log.warning("no_extractor_found", file=file_path.name)
                if not dry_run and portfolio.move_processed_files:
                    shutil.move(str(file_path), str(rejected / file_path.name))
                summary["files_rejected"] += 1
                continue

            if is_previdencia_file and portfolio_slug == "fundacao-ibm" and latest_previdencia_file is not None:
                if file_path != latest_previdencia_file:
                    log.info(
                        "previdencia_file_skipped_not_latest",
                        file=file_path.name,
                        latest=latest_previdencia_file.name,
                    )
                    if not dry_run and portfolio.move_processed_files:
                        shutil.move(str(file_path), str(processed / file_path.name))
                    summary["files_processed"] += 1
                    summary["skipped"] += 1
                    continue

            # Move to staging
            staged_path = staging / file_path.name
            if not dry_run:
                shutil.move(str(file_path), str(staged_path))
            else:
                staged_path = file_path

            file_hash = _sha256(staged_path)

            # Create import job
            job = ImportJob(
                portfolio_id=portfolio_id,
                source_type=(
                    "fixed_income_csv"
                    if is_fixed_income_file
                    else "previdencia_ibm_pdf"
                    if is_previdencia_file
                    else extractor.source_type
                ),
                file_name=staged_path.name,
                file_hash=file_hash,
                file_path=str(staged_path),
                status="processing",
            )
            job_id: int | None = None
            if not dry_run:
                job_id = job_repo.create(job)

            if is_fixed_income_file:
                file_result = _import_fixed_income_file(
                    portfolio_id=portfolio_id,
                    staged_path=staged_path,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_repo=job_repo,
                    fi_repo=fi_repo,
                )
                inserted = file_result["inserted"]
                skipped = file_result["skipped"]
                total = file_result["total"]
                error_count = file_result["errors"]
            elif is_previdencia_file and previdencia_extractor is not None:
                file_result = _import_previdencia_ibm_file(
                    portfolio_id=portfolio_id,
                    staged_path=staged_path,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_repo=job_repo,
                    prev_repo=prev_repo,
                    extractor=previdencia_extractor,
                )
                inserted = file_result["inserted"]
                skipped = file_result["skipped"]
                total = file_result["total"]
                error_count = file_result["errors"]
            else:
                # Extract (with per-file cache for slow extractors that opt in)
                cached_extraction = load_cached_extraction(
                    staged_path, extractor, file_hash=file_hash
                )
                if cached_extraction is not None:
                    extraction = cached_extraction
                    log.info("extraction_cache_hit", file=staged_path.name)
                else:
                    extraction = extractor.extract(staged_path)
                    save_cached_extraction(
                        staged_path, extractor, extraction, file_hash=file_hash
                    )

                # Log extraction errors
                if extraction.has_errors:
                    for err in extraction.errors:
                        log.warning(
                            "extraction_error",
                            file=staged_path.name,
                            error=err.get("message"),
                        )
                        if not dry_run and job_id:
                            job_repo.log_error(
                                job_id,
                                error_type=err.get("error_type", "parsing"),
                                message=err.get("message", ""),
                                row_index=err.get("row_index"),
                                raw_data=err.get("raw_data"),
                            )

                # Normalize
                norm_result = normalizer.normalize(
                    extraction.records, portfolio_id, import_job_id=job_id
                )

                for err in norm_result.errors:
                    log.warning(
                        "normalization_error",
                        file=staged_path.name,
                        row=err.row_index,
                        error=err.message,
                    )
                    if not dry_run and job_id:
                        job_repo.log_error(
                            job_id,
                            error_type=err.error_type,
                            message=err.message,
                            row_index=err.row_index,
                            field=err.field,
                            raw_data=err.raw_data,
                        )

                # Deduplicate within batch
                unique_ops, dup_ops = dedup_svc.deduplicate(
                    norm_result.valid, keys=portfolio.deduplicate_by
                )
                if dup_ops:
                    log.info(
                        "intra_batch_duplicates_removed",
                        count=len(dup_ops),
                        file=staged_path.name,
                    )

                # Persist
                inserted = 0
                skipped = len(dup_ops)
                if not dry_run and unique_ops:
                    inserted, db_skipped = op_repo.insert_many(unique_ops)
                    skipped += db_skipped

                    # Recalculate positions
                    all_ops = op_repo.list_all_by_portfolio(portfolio_id)
                    positions = pos_svc.calculate(all_ops, portfolio_id)
                    pos_repo.upsert_many(positions)

                total = len(extraction.records)
                error_count = len(extraction.errors) + len(norm_result.errors)

            if not dry_run and job_id:
                final_status = "done" if error_count == 0 else (
                    "partial" if inserted > 0 else "failed"
                )
                job_repo.update_status(
                    job_id,
                    status=final_status,
                    total_records=total,
                    valid_records=inserted,
                    skipped_records=skipped,
                    error_records=error_count,
                )

            # Move file to final destination
            if not dry_run and portfolio.move_processed_files:
                dest_dir = processed if error_count == 0 or inserted > 0 else rejected
                shutil.move(str(staged_path), str(dest_dir / staged_path.name))

            summary["files_processed"] += 1
            summary["total_records"] += total
            summary["inserted"] += inserted
            summary["skipped"] += skipped
            summary["errors"] += error_count

            log.info(
                "file_done",
                file=staged_path.name,
                total=total,
                inserted=inserted,
                skipped=skipped,
                errors=error_count,
                dry_run=dry_run,
            )

    # Checkpoint the WAL file so it doesn't grow unboundedly.
    if not dry_run:
        db.connection.commit()
        db.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

    log.info("import_complete", **summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import inbox files for a single portfolio."
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        help="Portfolio ID (folder name under portfolios/<owner>/).",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help=(
            "Owner ID (folder name under portfolios/). When omitted the "
            "portfolio is searched across all owner subfolders, then the "
            "legacy single-level layout."
        ),
    )
    parser.add_argument(
        "--db",
        default="ia_invest.db",
        help="Path to the SQLite database file (default: ia_invest.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate files without persisting any data.",
    )
    args = parser.parse_args()

    result = import_portfolio(
        args.portfolio,
        db_path=Path(args.db),
        dry_run=args.dry_run,
        owner_id=args.owner,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
