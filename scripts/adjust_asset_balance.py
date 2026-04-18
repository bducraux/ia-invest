"""Manual asset balance adjustment script.

This script asks for an asset and the real quantity currently held, compares it
with the portfolio quantity in the database, and inserts a correcting
transaction (buy/sell) using the current average price so the average price is
preserved after the adjustment.

Usage examples:

    uv run python scripts/adjust_asset_balance.py --portfolio cripto
    uv run python scripts/adjust_asset_balance.py --portfolio cripto --asset BTC --real-quantity 0.55076536
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from domain.models import Operation
from domain.position_service import PositionService
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.positions import PositionRepository

_BUY_TYPES = {"buy", "transfer_in", "split_bonus"}
_SELL_TYPES = {"sell", "transfer_out"}


def _to_decimal(raw: str) -> Decimal:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty numeric value")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid number: {raw!r}") from exc


def _compute_current_qty(db: Database, portfolio_id: str, asset_code: str) -> Decimal:
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


def _compute_current_avg_price_cents(
    db: Database, portfolio_id: str, asset_code: str
) -> int:
    """Calculate current avg price from a fresh position recalculation."""
    rows = db.connection.execute(
        """
        SELECT *
        FROM operations
        WHERE portfolio_id = ?
        ORDER BY operation_date ASC, id ASC
        """,
        (portfolio_id,),
    ).fetchall()

    ops = [dict(r) for r in rows]
    if not ops:
        return 0

    positions = PositionService().calculate(ops, portfolio_id)
    for pos in positions:
        if pos.asset_code.upper() == asset_code.upper():
            return int(pos.avg_price)
    return 0


def _build_external_id(
    portfolio_id: str,
    asset_code: str,
    operation_date: str,
    current_qty: Decimal,
    real_qty: Decimal,
) -> str:
    key = (
        f"manual_adjustment|{portfolio_id}|{asset_code}|{operation_date}|"
        f"{current_qty}|{real_qty}"
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _sync_positions(db: Database, portfolio_id: str) -> None:
    rows = db.connection.execute(
        """
        SELECT *
        FROM operations
        WHERE portfolio_id = ?
        ORDER BY operation_date ASC, id ASC
        """,
        (portfolio_id,),
    ).fetchall()
    ops = [dict(r) for r in rows]
    positions = PositionService().calculate(ops, portfolio_id) if ops else []
    PositionRepository(db.connection).upsert_many(positions)


def _prompt_if_missing(value: str | None, label: str) -> str:
    if value is not None:
        return value
    return input(f"{label}: ").strip()


def run_adjustment(
    *,
    db_path: Path,
    portfolio_id: str,
    asset_code: str,
    real_quantity: Decimal,
    notes: str | None = None,
    dry_run: bool = False,
) -> None:
    asset_code = asset_code.upper().strip()

    with Database(db_path) as db:
        db.initialize()

        current_qty = _compute_current_qty(db, portfolio_id, asset_code)
        current_avg_cents = _compute_current_avg_price_cents(db, portfolio_id, asset_code)

        print(f"Current {asset_code} quantity in portfolio '{portfolio_id}': {current_qty}")
        print(f"Current average price: {current_avg_cents / 100:.8f} BRL")
        print(f"Target real quantity: {real_quantity}")

        delta = real_quantity - current_qty
        if delta == 0:
            print("No adjustment needed. Quantities already match.")
            return

        operation_type = "buy" if delta > 0 else "sell"
        adjustment_qty = abs(delta)

        # Use current average price to keep average price unchanged after adjust.
        unit_price_cents = int(current_avg_cents)
        gross_value_cents = int((adjustment_qty * Decimal(unit_price_cents)).to_integral_value())

        op_date = date.today().isoformat()
        external_id = _build_external_id(
            portfolio_id, asset_code, op_date, current_qty, real_quantity
        )

        note = notes or (
            f"Ajuste manual de saldo ({asset_code}) "
            f"de {current_qty} para {real_quantity}"
        )

        op = Operation(
            portfolio_id=portfolio_id,
            source="manual_adjustment",
            external_id=external_id,
            asset_code=asset_code,
            asset_type="crypto",
            operation_type=operation_type,
            operation_date=op_date,
            quantity=float(adjustment_qty),
            unit_price=unit_price_cents,
            gross_value=gross_value_cents,
            fees=0,
            broker="manual",
            notes=note,
            raw_data={
                "reason": "manual_balance_adjustment",
                "current_qty": str(current_qty),
                "target_qty": str(real_quantity),
                "delta": str(delta),
                "preserve_avg_price": True,
                "avg_price_cents_used": unit_price_cents,
            },
        )

        if dry_run:
            print("Dry-run enabled: no data will be written.")
            print(
                f"Would insert operation: type={operation_type}, "
                f"qty={adjustment_qty}, unit_price={unit_price_cents / 100:.8f} BRL, "
                f"gross_value={gross_value_cents / 100:.8f} BRL"
            )
            print(f"Notes: {note}")
            print(f"Expected new {asset_code} quantity: {real_quantity}")
            print(f"Expected average price: {current_avg_cents / 100:.8f} BRL")
            return

        inserted, skipped = OperationRepository(db.connection).insert_many([op])
        if inserted != 1:
            print(
                "Adjustment was not inserted "
                f"(inserted={inserted}, skipped={skipped})."
            )
            return

        _sync_positions(db, portfolio_id)

        new_qty = _compute_current_qty(db, portfolio_id, asset_code)
        new_avg_cents = _compute_current_avg_price_cents(db, portfolio_id, asset_code)

        print("Adjustment inserted successfully.")
        print(
            f"Inserted operation: type={operation_type}, "
            f"qty={adjustment_qty}, unit_price={unit_price_cents / 100:.8f} BRL"
        )
        print(f"New {asset_code} quantity: {new_qty}")
        print(f"New average price: {new_avg_cents / 100:.8f} BRL")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Adjust an asset quantity to match real balance by inserting a "
            "manual operation at current average price."
        )
    )
    parser.add_argument("--portfolio", default="cripto", help="Portfolio ID")
    parser.add_argument("--db", default="ia_invest.db", help="SQLite DB path")
    parser.add_argument("--asset", help="Asset code (e.g., BTC)")
    parser.add_argument(
        "--real-quantity",
        help=(
            "Real quantity currently held. Supports dot or comma decimal "
            "notation, e.g. 0.55076536 or 0,55076536"
        ),
    )
    parser.add_argument(
        "--notes",
        help="Optional custom note for the adjustment operation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the adjustment without inserting anything into the database.",
    )

    args = parser.parse_args()

    asset_code = _prompt_if_missing(args.asset, "Asset code")
    raw_real_qty = _prompt_if_missing(args.real_quantity, "Real quantity")
    real_quantity = _to_decimal(raw_real_qty)

    run_adjustment(
        db_path=Path(args.db),
        portfolio_id=args.portfolio,
        asset_code=asset_code,
        real_quantity=real_quantity,
        notes=args.notes,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
