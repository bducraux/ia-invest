"""Sync historical monthly closing prices for all assets in the database.

Backfills the ``historical_prices`` cache for every distinct asset that
appears in ``operations`` (and previdência snapshots, opportunistically).
Closing prices are immutable, so this script only fetches gaps — running
it repeatedly is cheap.

Usage:

    uv run python scripts/sync_historical_prices.py
    uv run python scripts/sync_historical_prices.py --portfolio bob-renda-variavel
    uv run python scripts/sync_historical_prices.py --full
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

from mcp_server.services.historical_prices import HistoricalPriceService
from storage.repository.db import Database
from storage.repository.historical_prices import HistoricalPricesRepository

LOG = logging.getLogger("sync_historical_prices")


def _collect_assets(
    db: Database, portfolio_id: str | None
) -> list[tuple[str, str, date]]:
    """Return ``(asset_code, asset_type, first_op_date)`` triples.

    ``first_op_date`` lets the service request a tight time window per asset.
    """
    sql = (
        "SELECT asset_code, asset_type, MIN(operation_date) AS first_date "
        "FROM operations "
    )
    params: list[str] = []
    if portfolio_id is not None:
        sql += "WHERE portfolio_id = ? "
        params.append(portfolio_id)
    sql += "GROUP BY asset_code, asset_type ORDER BY asset_code"

    rows = db.connection.execute(sql, params).fetchall()
    out: list[tuple[str, str, date]] = []
    for row in rows:
        first = datetime.strptime(row["first_date"], "%Y-%m-%d").date()
        out.append((str(row["asset_code"]), str(row["asset_type"] or ""), first))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", help="Restrict to a single portfolio_id")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force a deeper backfill (5 anos antes da primeira operação).",
    )
    parser.add_argument(
        "--db", default=None, help="Path to ia_invest.db (defaults to env)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    db = Database(args.db) if args.db else Database()
    db.initialize()
    repo = HistoricalPricesRepository(db.connection)
    service = HistoricalPriceService(repo, timeout_seconds=8.0)

    assets = _collect_assets(db, args.portfolio)
    if not assets:
        LOG.info("Nenhum ativo encontrado em operations.")
        return 0

    today = date.today()
    summary: dict[str, int] = {"yahoo": 0, "cache_only": 0, "no_data": 0}
    for asset_code, asset_type, first_date in assets:
        # ``--full`` widens the window 5 years before the first op.
        backfill_start = (
            date(first_date.year - 5, 1, 1)
            if args.full
            else date(first_date.year, max(1, first_date.month - 1), 1)
        )
        result = service.backfill(asset_code, asset_type, backfill_start, today)
        summary[result.source] = summary.get(result.source, 0) + 1
        LOG.info(
            "%-10s %-10s rows=%-4d cov=%s..%s source=%s",
            asset_code,
            asset_type or "?",
            result.rows_inserted,
            result.coverage_start,
            result.coverage_end,
            result.source,
        )

    LOG.info("Total: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
