"""Import all active portfolios.

Iterates over all subdirectories of portfolios/ that contain a portfolio.yml
and runs import_portfolio for each.

Usage::

    python scripts/import_all.py
    python scripts/import_all.py --db path/to/ia_invest.db
    python scripts/import_all.py --dry-run
    python scripts/import_all.py --verbose
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import structlog

from scripts.import_portfolio import import_portfolio

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


def _count_inbox_files(portfolio_dir: Path) -> int:
    inbox = portfolio_dir / "inbox"
    if not inbox.exists():
        return 0
    return sum(
        1 for f in inbox.iterdir() if f.is_file() and not f.name.startswith(".")
    )


def _print_banner(text: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{text}\n{bar}", flush=True)


def _print_portfolio_header(index: int, total: int, name: str, file_count: int) -> None:
    bar = "-" * 72
    print(
        f"\n{bar}\n[{index}/{total}] Portfolio: {name}  (files in inbox: {file_count})\n{bar}",
        flush=True,
    )


def _print_portfolio_result(
    name: str, result: dict[str, Any], elapsed_s: float
) -> None:
    if "error" in result:
        print(f"  ✗ {name}: ERROR — {result['error']}  ({elapsed_s:.1f}s)", flush=True)
        return
    processed = result.get("files_processed", 0)
    rejected = result.get("files_rejected", 0)
    total_recs = result.get("total_records", 0)
    inserted = result.get("inserted", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", 0)
    status = "✓" if errors == 0 and rejected == 0 else "⚠"
    print(
        f"  {status} {name}: files={processed} rejected={rejected} "
        f"records={total_recs} inserted={inserted} skipped={skipped} "
        f"errors={errors}  ({elapsed_s:.1f}s)",
        flush=True,
    )


def _print_final_summary(
    aggregate: dict[str, int], elapsed_s: float, error_count: int
) -> None:
    _print_banner("IMPORT ALL — FINAL SUMMARY")
    print(
        f"  portfolios:       {aggregate['portfolios']}\n"
        f"  files_processed:  {aggregate['files_processed']}\n"
        f"  files_rejected:   {aggregate['files_rejected']}\n"
        f"  total_records:    {aggregate['total_records']}\n"
        f"  inserted:         {aggregate['inserted']}\n"
        f"  skipped:          {aggregate['skipped']}\n"
        f"  normalization/extraction errors: {aggregate['errors']}\n"
        f"  failed portfolios: {error_count}\n"
        f"  elapsed:          {elapsed_s:.1f}s",
        flush=True,
    )


def _discover_portfolio_dirs(root: Path) -> list[Path]:
    """Return all portfolio directories, scanning the new
    ``portfolios/<owner>/<portfolio>/`` layout *and* the legacy
    ``portfolios/<portfolio>/`` single-level layout for backward
    compatibility.
    """
    if not root.exists():
        return []

    portfolios: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        # Legacy single-level layout (no owner directory)
        if (child / "portfolio.yml").exists():
            portfolios.append(child)
            continue
        # New layout — child is an owner directory containing portfolios.
        for grandchild in sorted(child.iterdir()):
            if grandchild.is_dir() and (grandchild / "portfolio.yml").exists():
                portfolios.append(grandchild)
    return portfolios


def main() -> None:
    parser = argparse.ArgumentParser(description="Import all portfolios.")
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print human-readable banners and per-portfolio summaries to stdout.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    portfolio_dirs = _discover_portfolio_dirs(_PORTFOLIOS_DIR)

    if not portfolio_dirs:
        log.warning("no_portfolios_found", path=str(_PORTFOLIOS_DIR))
        sys.exit(0)

    log.info(
        "starting_import_all",
        portfolios=[
            f"{d.parent.name}/{d.name}" if d.parent != _PORTFOLIOS_DIR else d.name
            for d in portfolio_dirs
        ],
    )

    if args.verbose:
        total_inbox = sum(_count_inbox_files(d) for d in portfolio_dirs)
        _print_banner(
            f"IMPORT ALL — {len(portfolio_dirs)} portfolios, "
            f"{total_inbox} file(s) in inbox"
            + ("  [DRY-RUN]" if args.dry_run else "")
        )

    overall_errors = 0
    aggregate = {
        "portfolios": len(portfolio_dirs),
        "files_processed": 0,
        "files_rejected": 0,
        "total_records": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
    }
    started_all = time.monotonic()

    for index, portfolio_dir in enumerate(portfolio_dirs, start=1):
        owner = portfolio_dir.parent.name if portfolio_dir.parent != _PORTFOLIOS_DIR else None
        display_name = (
            f"{owner}/{portfolio_dir.name}" if owner else portfolio_dir.name
        )
        if args.verbose:
            _print_portfolio_header(
                index,
                len(portfolio_dirs),
                display_name,
                _count_inbox_files(portfolio_dir),
            )

        log.info(
            "importing_portfolio",
            portfolio=portfolio_dir.name,
            owner=owner,
        )
        started = time.monotonic()
        result = import_portfolio(
            portfolio_dir.name,
            db_path=db_path,
            dry_run=args.dry_run,
            owner_id=owner,
        )
        elapsed = time.monotonic() - started

        if "error" in result:
            log.error(
                "portfolio_import_failed",
                portfolio=portfolio_dir.name,
                error=result["error"],
            )
            overall_errors += 1
        else:
            for key in ("files_processed", "files_rejected", "total_records",
                        "inserted", "skipped", "errors"):
                aggregate[key] += int(result.get(key, 0))

        if args.verbose:
            _print_portfolio_result(display_name, result, elapsed)

    elapsed_all = time.monotonic() - started_all

    if args.verbose:
        _print_final_summary(aggregate, elapsed_all, overall_errors)

    if overall_errors:
        log.error("import_all_finished_with_errors", error_count=overall_errors)
        sys.exit(1)

    log.info("import_all_done")


if __name__ == "__main__":
    main()
