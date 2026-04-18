"""Check current asset balances from portfolio operations.

This script computes the net quantity per asset directly from operations,
without requiring direct DB queries.

Usage examples:

    uv run python scripts/check_asset_balance.py --portfolio cripto
    uv run python scripts/check_asset_balance.py --portfolio cripto --assets BTC,ETH
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from storage.repository.db import Database


def _prompt_assets_if_missing(raw_assets: str | None) -> str:
    if raw_assets is not None and raw_assets.strip():
        return raw_assets
    return input("Assets to check (comma-separated, e.g. BTC,ETH): ").strip()


def _parse_assets(raw_assets: str) -> list[str]:
    assets: list[str] = []
    seen: set[str] = set()
    for token in raw_assets.split(","):
        asset = token.strip().upper()
        if not asset:
            continue
        if asset not in seen:
            seen.add(asset)
            assets.append(asset)
    if not assets:
        raise ValueError("No valid assets provided.")
    return assets


def _get_net_quantity(db: Database, portfolio_id: str, asset_code: str) -> Decimal:
    row = db.connection.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN operation_type IN ('buy', 'transfer_in', 'split_bonus') THEN quantity
                        WHEN operation_type IN ('sell', 'transfer_out') THEN -quantity
                        ELSE 0
                    END
                ),
                0
            ) AS qty
        FROM operations
        WHERE portfolio_id = ? AND asset_code = ?
        """,
        (portfolio_id, asset_code),
    ).fetchone()
    return Decimal(str(row["qty"])) if row else Decimal("0")


def _get_position_quantity(db: Database, portfolio_id: str, asset_code: str) -> Decimal:
    row = db.connection.execute(
        """
        SELECT quantity
        FROM positions
        WHERE portfolio_id = ? AND asset_code = ?
        """,
        (portfolio_id, asset_code),
    ).fetchone()
    if row is None:
        return Decimal("0")
    return Decimal(str(row["quantity"]))


def run_check(*, db_path: Path, portfolio_id: str, assets: list[str]) -> None:
    with Database(db_path) as db:
        db.initialize()

        print(f"Portfolio: {portfolio_id}")
        print()
        print(
            "{:<8} {:>18} {:>18} {:>18}".format(
                "Asset", "Net (operations)", "Position table", "Difference"
            )
        )
        print("-" * 66)

        for asset in assets:
            net_qty = _get_net_quantity(db, portfolio_id, asset)
            pos_qty = _get_position_quantity(db, portfolio_id, asset)
            diff = pos_qty - net_qty
            print(
                "{:<8} {:>18} {:>18} {:>18}".format(
                    asset,
                    f"{net_qty:.8f}",
                    f"{pos_qty:.8f}",
                    f"{diff:.8f}",
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check one or more asset balances without manual DB queries."
    )
    parser.add_argument("--portfolio", default="cripto", help="Portfolio ID")
    parser.add_argument("--db", default="ia_invest.db", help="SQLite DB path")
    parser.add_argument(
        "--assets",
        help="Comma-separated assets to check, e.g. BTC,ETH",
    )

    args = parser.parse_args()
    raw_assets = _prompt_assets_if_missing(args.assets)
    assets = _parse_assets(raw_assets)

    run_check(
        db_path=Path(args.db),
        portfolio_id=args.portfolio,
        assets=assets,
    )


if __name__ == "__main__":
    main()
