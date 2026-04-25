"""Sync historical USD/BRL PTAX rates from BACEN SGS into the SQLite cache.

Usage::

    python scripts/sync_fx_rates.py                   # incremental USDBRL since last cache row
    python scripts/sync_fx_rates.py --full            # full bootstrap from 2018-01-01
    python scripts/sync_fx_rates.py --pair USDBRL --from 2024-01-01 --to 2024-12-31
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from mcp_server.services.fx_rates import SUPPORTED_PAIRS
from mcp_server.services.fx_sync import (
    DEFAULT_BOOTSTRAP_START,
    FxSyncError,
    FxSyncService,
)
from storage.repository.db import Database
from storage.repository.fx_rates import FxRatesRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync historical FX rates (PTAX) from BACEN into SQLite.")
    parser.add_argument("--db", default="ia_invest.db", help="Path to SQLite database")
    parser.add_argument("--pair", default="USDBRL", help=f"Currency pair to sync ({'/'.join(SUPPORTED_PAIRS)})")
    parser.add_argument("--from", dest="start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--full",
        action="store_true",
        help=f"Full refresh from {DEFAULT_BOOTSTRAP_START.isoformat()} — ignores cached coverage",
    )
    args = parser.parse_args()

    pair = args.pair.upper()
    if pair not in SUPPORTED_PAIRS:
        print(f"ERROR: unsupported pair '{pair}'. Supported: {', '.join(SUPPORTED_PAIRS)}")
        return 1

    db = Database(Path(args.db))
    db.initialize()
    repo = FxRatesRepository(db.connection)
    service = FxSyncService(repo, timeout_seconds=30.0)

    start = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    end: date | None = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None

    try:
        result = service.sync(
            pair, start_date=start, end_date=end, full_refresh=args.full
        )
    except FxSyncError as exc:
        print(f"ERROR: {exc}")
        return 1

    if result.rows_inserted == 0 and start is None and not args.full:
        print(
            f"{pair}: already up-to-date "
            f"(coverage {result.coverage_start} → {result.coverage_end})"
        )
        return 0

    print(
        f"{pair}: inserted {result.rows_inserted} row(s); "
        f"coverage = {result.coverage_start} → {result.coverage_end} "
        f"(source: {result.source})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
