"""Sync historical daily benchmark rates from BACEN SGS into the SQLite cache.

Usage::

    python scripts/sync_benchmark_rates.py            # incremental CDI sync
    python scripts/sync_benchmark_rates.py --full     # full bootstrap (since 2018-01-01)
    python scripts/sync_benchmark_rates.py --benchmark CDI --from 2024-01-01 --to 2024-12-31
    make sync-cdi
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from mcp_server.services.benchmark_sync import BACENBenchmarkSyncService, BenchmarkSyncError
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync historical CDI/Selic from BACEN SGS into SQLite.")
    parser.add_argument("--db", default="ia_invest.db", help="Path to SQLite database")
    parser.add_argument("--benchmark", default="CDI", help="Benchmark to sync (CDI, SELIC)")
    parser.add_argument("--from", dest="start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full refresh from the bootstrap default (2018-01-01) — ignores cached coverage",
    )
    args = parser.parse_args()

    db = Database(Path(args.db))
    db.initialize()
    repo = BenchmarkRatesRepository(db.connection)
    service = BACENBenchmarkSyncService(repo)

    start = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None

    try:
        result = service.sync(
            args.benchmark,
            start_date=start,
            end_date=end,
            full_refresh=args.full,
        )
    except BenchmarkSyncError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        f"{result.benchmark}: inserted {result.rows_inserted} row(s); "
        f"coverage = {result.coverage_start} → {result.coverage_end} (source: {result.source})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
