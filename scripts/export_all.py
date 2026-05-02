"""Export all portfolios to re-importable CSVs.

Iterates over every portfolio in the SQLite database and runs the
``PortfolioExportService`` for each one. Files are written under each
portfolio's ``portfolios/<owner>/<slug>/exports/`` directory.

Usage::

    python scripts/export_all.py
    python scripts/export_all.py --db path/to/ia_invest.db
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

from mcp_server.services.portfolio_export import PortfolioExportService
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
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


def _print_banner(text: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{text}\n{bar}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all portfolios to re-importable CSVs."
    )
    parser.add_argument(
        "--db",
        default="ia_invest.db",
        help="Path to the SQLite database file (default: ia_invest.db)",
    )
    parser.add_argument(
        "--portfolios-root",
        default="portfolios",
        help="Root directory where exports are written (default: portfolios)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("database_not_found", path=str(db_path))
        sys.exit(1)

    db = Database(str(db_path))
    db.initialize()
    conn = db.connection

    portfolio_repo = PortfolioRepository(conn)
    portfolios = portfolio_repo.list_all()
    if not portfolios:
        log.warning("no_portfolios_found", db=str(db_path))
        sys.exit(0)

    service = PortfolioExportService(
        operation_repo=OperationRepository(conn),
        fixed_income_repo=FixedIncomePositionRepository(conn),
        portfolio_repo=portfolio_repo,
        previdencia_repo=PrevidenciaSnapshotRepository(conn),
        portfolios_root=Path(args.portfolios_root),
    )

    _print_banner(f"EXPORT ALL — {len(portfolios)} portfolios")

    started_all = time.monotonic()
    total_files = 0
    total_rows = 0
    failed = 0

    for index, portfolio in enumerate(portfolios, start=1):
        started = time.monotonic()
        try:
            result = service.export(portfolio.id)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            log.error(
                "portfolio_export_failed",
                portfolio_id=portfolio.id,
                error=str(exc),
            )
            print(
                f"  ✗ [{index}/{len(portfolios)}] {portfolio.id}: ERROR — {exc}  "
                f"({elapsed:.1f}s)",
                flush=True,
            )
            failed += 1
            continue

        elapsed = time.monotonic() - started
        rows_in_portfolio = sum(int(f["rows"]) for f in result.files)
        total_files += result.total_files
        total_rows += rows_in_portfolio

        if result.total_files == 0:
            print(
                f"  · [{index}/{len(portfolios)}] {portfolio.id}: nothing to export  "
                f"({elapsed:.1f}s)",
                flush=True,
            )
        else:
            print(
                f"  ✓ [{index}/{len(portfolios)}] {portfolio.id}: "
                f"{result.total_files} file(s), {rows_in_portfolio} row(s) → "
                f"{result.output_dir}  ({elapsed:.1f}s)",
                flush=True,
            )
            for entry in result.files:
                file_name = Path(str(entry["path"])).name
                print(f"      - {file_name} ({entry['rows']} rows)", flush=True)

    elapsed_all = time.monotonic() - started_all
    _print_banner("EXPORT ALL — FINAL SUMMARY")
    print(
        f"  portfolios:  {len(portfolios)}\n"
        f"  files:       {total_files}\n"
        f"  rows:        {total_rows}\n"
        f"  failed:      {failed}\n"
        f"  elapsed:     {elapsed_all:.1f}s",
        flush=True,
    )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
