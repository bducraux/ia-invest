"""Print a rich overview of all assets in a portfolio.

Shows per-asset: quantity held, total cost, average buy price, first/last
operation date, number of operations, and a breakdown by operation type.

Usage::

    uv run python scripts/portfolio_overview.py
    uv run python scripts/portfolio_overview.py --portfolio cripto
    uv run python scripts/portfolio_overview.py --portfolio cripto --sort cost
    uv run python scripts/portfolio_overview.py --portfolio cripto --hide-zero
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from storage.repository.db import Database

_SORT_CHOICES = ("asset", "quantity", "cost", "avg_price", "ops", "date")


def _cents_to_brl(value: int | float | Decimal | None) -> float:
    if value is None:
        return 0.0
    return float(value) / 100.0


def _format_number_br(value: int | float | Decimal, decimals: int = 2) -> str:
    formatted = f"{float(value):,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _prompt_portfolio_if_missing(portfolio_id: str | None, db: Database) -> str:
    if portfolio_id:
        return portfolio_id

    rows = db.connection.execute(
        "SELECT id, name FROM portfolios ORDER BY id"
    ).fetchall()

    if not rows:
        raise SystemExit("No portfolios found in the database.")

    if len(rows) == 1:
        return rows[0]["id"]

    print("Available portfolios:")
    for i, row in enumerate(rows, 1):
        print(f"  {i}. {row['id']}  ({row['name']})")
    print()
    choice = input("Enter portfolio id or number: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(rows):
            return rows[idx]["id"]
    return choice


def _fetch_positions(db: Database, portfolio_id: str) -> list[dict]:
    return db.connection.execute(
        """
        SELECT
            asset_code,
            asset_type,
            quantity,
            avg_price,
            total_cost,
            first_operation_date,
            last_operation_date
        FROM positions
        WHERE portfolio_id = ?
        ORDER BY asset_code
        """,
        (portfolio_id,),
    ).fetchall()


def _fetch_op_summary(db: Database, portfolio_id: str) -> dict[str, dict]:
    """Return per-asset operation counts and type breakdown."""
    rows = db.connection.execute(
        """
        SELECT
            asset_code,
            operation_type,
            COUNT(*)          AS cnt,
            SUM(quantity)     AS total_qty,
            SUM(gross_value)  AS total_gross
        FROM operations
        WHERE portfolio_id = ?
          AND operation_type NOT IN ('transfer_in', 'transfer_out')  -- skip quote legs
        GROUP BY asset_code, operation_type
        """,
        (portfolio_id,),
    ).fetchall()

    summary: dict[str, dict] = {}
    for row in rows:
        code = row["asset_code"]
        if code not in summary:
            summary[code] = {"total_ops": 0, "by_type": {}}
        summary[code]["total_ops"] += row["cnt"]
        summary[code]["by_type"][row["operation_type"]] = {
            "count": row["cnt"],
            "qty": Decimal(str(row["total_qty"] or 0)),
            "gross": Decimal(str(row["total_gross"] or 0)),
        }
    return summary


def _fetch_portfolio_name(db: Database, portfolio_id: str) -> str:
    row = db.connection.execute(
        "SELECT name FROM portfolios WHERE id = ?", (portfolio_id,)
    ).fetchone()
    return row["name"] if row else portfolio_id


def _sort_key(pos: dict, op_summary: dict, sort: str):
    code = pos["asset_code"]
    if sort == "quantity":
        return -abs(float(pos["quantity"] or 0))
    if sort == "cost":
        return -float(pos["total_cost"] or 0)
    if sort == "avg_price":
        return -float(pos["avg_price"] or 0)
    if sort == "ops":
        return -(op_summary.get(code, {}).get("total_ops", 0))
    if sort == "date":
        return pos["last_operation_date"] or ""
    return pos["asset_code"]  # default: alphabetical


def run_overview(
    *,
    db_path: Path,
    portfolio_id: str | None,
    sort: str,
    hide_zero: bool,
) -> None:
    with Database(db_path) as db:
        db.initialize()

        portfolio_id = _prompt_portfolio_if_missing(portfolio_id, db)
        portfolio_name = _fetch_portfolio_name(db, portfolio_id)

        positions = _fetch_positions(db, portfolio_id)
        op_summary = _fetch_op_summary(db, portfolio_id)

        if not positions:
            print(f"No positions found for portfolio '{portfolio_id}'.")
            return

        if hide_zero:
            positions = [p for p in positions if float(p["quantity"] or 0) != 0.0]

        positions = sorted(positions, key=lambda p: _sort_key(p, op_summary, sort))

        # -----------------------------------------------------------------------
        # Header
        # -----------------------------------------------------------------------
        sep = "─" * 110
        print()
        print(f"  Portfolio  : {portfolio_name}  ({portfolio_id})")
        print(f"  Assets     : {len(positions)}")
        total_cost = sum(_cents_to_brl(p["total_cost"] or 0) for p in positions)
        print(f"  Total cost : R$ {_format_number_br(total_cost, 2)}")
        print()
        print(sep)
        print(
            f"  {'Asset':<8}  {'Type':<8}  {'Quantity':>20}  {'Avg Price (BRL)':>16}  "
            f"{'Total Cost (BRL)':>16}  {'Ops':>5}  {'First op':>12}  {'Last op':>12}"
        )
        print(sep)

        for pos in positions:
            code = pos["asset_code"]
            ops = op_summary.get(code, {})
            total_ops = ops.get("total_ops", 0)

            qty = float(pos["quantity"] or 0)
            qty_str = f"{_format_number_br(qty, 8):>20}"
            # Flag negatives
            if qty < 0:
                qty_str = f"{'⚠ ' + _format_number_br(qty, 8):>20}"

            avg_price = _cents_to_brl(pos["avg_price"] or 0)
            cost = _cents_to_brl(pos["total_cost"] or 0)

            print(
                f"  {code:<8}  {(pos['asset_type'] or ''):<8}  {qty_str}  "
                f"{_format_number_br(avg_price, 2):>16}  {_format_number_br(cost, 2):>16}  {total_ops:>5}  "
                f"{pos['first_operation_date'] or '-':>12}  {pos['last_operation_date'] or '-':>12}"
            )

        print(sep)

        # -----------------------------------------------------------------------
        # Per-asset detail: buy vs sell breakdown
        # -----------------------------------------------------------------------
        print()
        print("  Operation breakdown (buys / sells only, excluding quote legs)")
        print()
        print(
            f"  {'Asset':<8}  {'Buys':>5}  {'Qty Bought':>18}  {'BRL Spent':>15}  "
            f"{'Sells':>5}  {'Qty Sold':>18}"
        )
        print("─" * 82)

        total_spent = Decimal("0")

        for pos in positions:
            code = pos["asset_code"]
            by_type = op_summary.get(code, {}).get("by_type", {})

            buy = by_type.get("buy", {})
            sell = by_type.get("sell", {})

            b_cnt = buy.get("count", 0)
            b_qty = buy.get("qty", Decimal("0"))
            b_gross = buy.get("gross", Decimal("0"))

            s_cnt = sell.get("count", 0)
            s_qty = sell.get("qty", Decimal("0"))
            s_gross = sell.get("gross", Decimal("0"))

            total_spent += b_gross

            print(
                f"  {code:<8}  {b_cnt:>5}  {_format_number_br(b_qty, 8):>18}  {_format_number_br(_cents_to_brl(b_gross), 2):>15}  "
                f"{s_cnt:>5}  {_format_number_br(s_qty, 8):>18}"
            )

        print("─" * 82)
        print(
            f"  {'TOTAL':<8}  {'':>5}  {'':>18}  {_format_number_br(_cents_to_brl(total_spent), 2):>15}  "
            f"{'':>5}  {'':>18}"
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio overview — all assets summary.")
    parser.add_argument("--portfolio", "-p", default=None, help="Portfolio ID")
    parser.add_argument(
        "--db", default="ia_invest.db", help="Path to the SQLite database (default: ia_invest.db)"
    )
    parser.add_argument(
        "--sort",
        choices=_SORT_CHOICES,
        default="asset",
        help="Sort assets by: asset (default), quantity, cost, avg_price, ops, date",
    )
    parser.add_argument(
        "--hide-zero",
        action="store_true",
        help="Hide assets with zero quantity",
    )
    args = parser.parse_args()

    run_overview(
        db_path=Path(args.db),
        portfolio_id=args.portfolio,
        sort=args.sort,
        hide_zero=args.hide_zero,
    )


if __name__ == "__main__":
    main()
