"""Import all active portfolios.

Iterates over all subdirectories of portfolios/ that contain a portfolio.yml
and runs import_portfolio for each.

Usage::

    python scripts/import_all.py
    python scripts/import_all.py --db path/to/ia_invest.db
    python scripts/import_all.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog  # noqa: E402

from scripts.import_portfolio import import_portfolio  # noqa: E402

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
    args = parser.parse_args()

    db_path = Path(args.db)

    portfolio_dirs = [
        d for d in _PORTFOLIOS_DIR.iterdir()
        if d.is_dir() and (d / "portfolio.yml").exists()
    ]

    if not portfolio_dirs:
        log.warning("no_portfolios_found", path=str(_PORTFOLIOS_DIR))
        sys.exit(0)

    log.info("starting_import_all", portfolios=[d.name for d in portfolio_dirs])

    overall_errors = 0
    for portfolio_dir in sorted(portfolio_dirs):
        log.info("importing_portfolio", portfolio=portfolio_dir.name)
        result = import_portfolio(
            portfolio_dir.name,
            db_path=db_path,
            dry_run=args.dry_run,
        )
        if "error" in result:
            log.error("portfolio_import_failed", portfolio=portfolio_dir.name, error=result["error"])
            overall_errors += 1

    if overall_errors:
        log.error("import_all_finished_with_errors", error_count=overall_errors)
        sys.exit(1)

    log.info("import_all_done")


if __name__ == "__main__":
    main()
