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
import hashlib
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog  # noqa: E402

from domain.deduplication import DeduplicationService  # noqa: E402
from domain.models import ImportJob  # noqa: E402
from domain.portfolio_service import PortfolioService  # noqa: E402
from domain.position_service import PositionService  # noqa: E402
from extractors import get_extractor, list_source_types  # noqa: E402
from normalizers.operations import OperationNormalizer  # noqa: E402
from storage.repository.db import Database  # noqa: E402
from storage.repository.import_jobs import ImportJobRepository  # noqa: E402
from storage.repository.operations import OperationRepository  # noqa: E402
from storage.repository.portfolios import PortfolioRepository  # noqa: E402
from storage.repository.positions import PositionRepository  # noqa: E402

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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_extractor_for_file(file_path: Path, enabled_sources: list[str]) -> Any | None:
    """Find the first enabled extractor that can handle the file."""
    for source_type in enabled_sources:
        try:
            extractor = get_extractor(source_type)
            if extractor.can_handle(file_path):
                return extractor
        except KeyError:
            log.warning("unknown_source_type", source_type=source_type)
    return None


def import_portfolio(
    portfolio_id: str,
    *,
    db_path: Path = Path("ia_invest.db"),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import all inbox files for the given portfolio.

    Returns a summary dict with counts and status.
    """
    portfolio_dir = _PORTFOLIOS_DIR / portfolio_id
    manifest_path = portfolio_dir / "portfolio.yml"

    if not portfolio_dir.exists():
        log.error("portfolio_dir_not_found", path=str(portfolio_dir))
        return {"error": f"Portfolio directory not found: {portfolio_dir}"}

    # Load and validate portfolio manifest
    portfolio_svc = PortfolioService()
    try:
        portfolio = portfolio_svc.load_from_yaml(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        log.error("manifest_error", error=str(exc))
        return {"error": str(exc)}

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

        # Ensure portfolio is registered in DB
        portfolio_repo = PortfolioRepository(db.connection)
        portfolio_repo.upsert(portfolio)

        op_repo = OperationRepository(db.connection)
        pos_repo = PositionRepository(db.connection)
        job_repo = ImportJobRepository(db.connection)
        normalizer = OperationNormalizer()
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

        for file_path in sorted(files):
            log.info("processing_file", file=file_path.name, portfolio=portfolio_id)

            extractor = _find_extractor_for_file(file_path, enabled_sources)
            if extractor is None:
                log.warning("no_extractor_found", file=file_path.name)
                if not dry_run and portfolio.move_processed_files:
                    shutil.move(str(file_path), str(rejected / file_path.name))
                summary["files_rejected"] += 1
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
                source_type=extractor.source_type,
                file_name=staged_path.name,
                file_hash=file_hash,
                file_path=str(staged_path),
                status="processing",
            )
            job_id: int | None = None
            if not dry_run:
                job_id = job_repo.create(job)

            # Extract
            extraction = extractor.extract(staged_path)

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
                all_ops = op_repo.list_by_portfolio(portfolio_id)
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

    log.info("import_complete", **summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import inbox files for a single portfolio."
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        help="Portfolio ID (must match a subfolder under portfolios/)",
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
    )

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
