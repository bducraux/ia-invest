"""Position repository — read and update materialised positions."""

from __future__ import annotations

import sqlite3
from typing import Any

from domain.models import Position


class PositionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, position: Position) -> None:
        self._upsert_execute(position)
        self._conn.commit()

    def upsert_many(self, positions: list[Position]) -> None:
        for pos in positions:
            self._upsert_execute(pos)
        self._conn.commit()

    def _upsert_execute(self, position: Position) -> None:
        self._conn.execute(
            """
            INSERT INTO positions (
                portfolio_id, asset_code, asset_type, asset_name,
                quantity, avg_price, total_cost, realized_pnl, dividends,
                first_operation_date, last_operation_date, updated_at
            ) VALUES (
                :portfolio_id, :asset_code, :asset_type, :asset_name,
                :quantity, :avg_price, :total_cost, :realized_pnl, :dividends,
                :first_operation_date, :last_operation_date,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
            ON CONFLICT(portfolio_id, asset_code) DO UPDATE SET
                asset_type           = excluded.asset_type,
                asset_name           = excluded.asset_name,
                quantity             = excluded.quantity,
                avg_price            = excluded.avg_price,
                total_cost           = excluded.total_cost,
                realized_pnl         = excluded.realized_pnl,
                dividends            = excluded.dividends,
                first_operation_date = excluded.first_operation_date,
                last_operation_date  = excluded.last_operation_date,
                updated_at           = excluded.updated_at
            """,
            {
                "portfolio_id": position.portfolio_id,
                "asset_code": position.asset_code,
                "asset_type": position.asset_type,
                "asset_name": position.asset_name,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "total_cost": position.total_cost,
                "realized_pnl": position.realized_pnl,
                "dividends": position.dividends,
                "first_operation_date": position.first_operation_date,
                "last_operation_date": position.last_operation_date,
            },
        )

    def get(self, portfolio_id: str, asset_code: str) -> Position | None:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE portfolio_id = ? AND asset_code = ?",
            (portfolio_id, asset_code),
        ).fetchone()
        return self._row_to_position(row) if row else None

    def list_by_portfolio(self, portfolio_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM positions
            WHERE portfolio_id = ?
            ORDER BY asset_code
            """,
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_open_by_portfolio(self, portfolio_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM positions
            WHERE portfolio_id = ? AND quantity > 0
            ORDER BY asset_code
            """,
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> Position:
        return Position(
            portfolio_id=row["portfolio_id"],
            asset_code=row["asset_code"],
            asset_type=row["asset_type"],
            asset_name=row["asset_name"],
            quantity=row["quantity"],
            avg_price=row["avg_price"],
            total_cost=row["total_cost"],
            realized_pnl=row["realized_pnl"],
            dividends=row["dividends"],
            first_operation_date=row["first_operation_date"],
            last_operation_date=row["last_operation_date"],
        )
