"""Operation repository — insert and query normalised operations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from domain.models import Operation


class OperationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, operations: list[Operation]) -> tuple[int, int]:
        """Insert a batch of operations.

        Returns:
            (inserted, skipped) — skipped means duplicate (UNIQUE constraint).
        """
        inserted = 0
        skipped = 0
        for op in operations:
            try:
                self._conn.execute(
                    """
                    INSERT INTO operations (
                        portfolio_id, import_job_id, source, external_id,
                        asset_code, asset_type, asset_name,
                        operation_type, operation_date, settlement_date,
                        quantity, unit_price, gross_value, fees, net_value,
                        trade_currency, unit_price_native, gross_value_native,
                        fees_native, fx_rate_at_trade, fx_rate_source,
                        broker, account, notes, raw_data_json
                    ) VALUES (
                        :portfolio_id, :import_job_id, :source, :external_id,
                        :asset_code, :asset_type, :asset_name,
                        :operation_type, :operation_date, :settlement_date,
                        :quantity, :unit_price, :gross_value, :fees, :net_value,
                        :trade_currency, :unit_price_native, :gross_value_native,
                        :fees_native, :fx_rate_at_trade, :fx_rate_source,
                        :broker, :account, :notes, :raw_data_json
                    )
                    """,
                    {
                        "portfolio_id": op.portfolio_id,
                        "import_job_id": op.import_job_id,
                        "source": op.source,
                        "external_id": op.external_id,
                        "asset_code": op.asset_code,
                        "asset_type": op.asset_type,
                        "asset_name": op.asset_name,
                        "operation_type": op.operation_type,
                        "operation_date": op.operation_date,
                        "settlement_date": op.settlement_date,
                        "quantity": op.quantity,
                        "unit_price": op.unit_price,
                        "gross_value": op.gross_value,
                        "fees": op.fees,
                        "net_value": op.net_value,
                        "trade_currency": op.trade_currency,
                        "unit_price_native": op.unit_price_native,
                        "gross_value_native": op.gross_value_native,
                        "fees_native": op.fees_native,
                        "fx_rate_at_trade": op.fx_rate_at_trade,
                        "fx_rate_source": op.fx_rate_source,
                        "broker": op.broker,
                        "account": op.account,
                        "notes": op.notes,
                        "raw_data_json": (
                            json.dumps(op.raw_data) if op.raw_data else None
                        ),
                    },
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return inserted, skipped

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        asset_code: str | None = None,
        operation_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions = ["portfolio_id = ?"]
        params: list[Any] = [portfolio_id]

        if asset_code:
            conditions.append("asset_code = ?")
            params.append(asset_code)
        if operation_type:
            conditions.append("operation_type = ?")
            params.append(operation_type)
        if start_date:
            conditions.append("operation_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("operation_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions)
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"""
            SELECT * FROM operations
            WHERE {where}
            ORDER BY operation_date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Single-row CRUD
    # ------------------------------------------------------------------

    def get(self, operation_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
        return dict(row) if row else None

    # Whitelist of fields that can be edited via update().
    _UPDATABLE_FIELDS: tuple[str, ...] = (
        "asset_code",
        "asset_name",
        "asset_type",
        "operation_type",
        "operation_date",
        "settlement_date",
        "quantity",
        "unit_price",
        "gross_value",
        "fees",
        "net_value",
        "notes",
        "broker",
        "account",
    )

    def update(
        self,
        operation_id: int,
        portfolio_id: str,
        fields: dict[str, Any],
        *,
        commit: bool = True,
    ) -> int:
        """Update whitelisted fields of an operation.

        Returns the number of affected rows (0 or 1). The ``external_id``
        column is rewritten to ``manual:edited:{id}`` on every edit so a
        future reimport of the original source file keeps inserting cleanly
        without colliding with this now-divergent row.
        """
        unknown = set(fields) - set(self._UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"Cannot update fields: {sorted(unknown)}")
        if not fields:
            return 0

        assignments = ", ".join(f"{col} = :{col}" for col in fields)
        params: dict[str, Any] = dict(fields)
        params["id"] = operation_id
        params["portfolio_id"] = portfolio_id
        params["edited_external_id"] = f"manual:edited:{operation_id}"

        cur = self._conn.execute(
            f"""
            UPDATE operations
            SET {assignments},
                external_id = :edited_external_id
            WHERE id = :id AND portfolio_id = :portfolio_id
            """,
            params,
        )
        if commit:
            self._conn.commit()
        return cur.rowcount

    def delete(
        self,
        operation_id: int,
        portfolio_id: str,
        *,
        commit: bool = True,
    ) -> int:
        cur = self._conn.execute(
            "DELETE FROM operations WHERE id = ? AND portfolio_id = ?",
            (operation_id, portfolio_id),
        )
        if commit:
            self._conn.commit()
        return cur.rowcount

    def delete_by_asset(
        self,
        portfolio_id: str,
        asset_code: str,
        *,
        commit: bool = True,
    ) -> int:
        cur = self._conn.execute(
            "DELETE FROM operations WHERE portfolio_id = ? AND asset_code = ?",
            (portfolio_id, asset_code),
        )
        if commit:
            self._conn.commit()
        return cur.rowcount

    def count_by_asset(self, portfolio_id: str, asset_code: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM operations WHERE portfolio_id = ? AND asset_code = ?",
            (portfolio_id, asset_code),
        ).fetchone()
        return int(row["n"]) if row else 0

    def list_all_by_portfolio(
        self,
        portfolio_id: str,
        *,
        asset_code: str | None = None,
        operation_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all operations for a portfolio (no pagination)."""
        conditions = ["portfolio_id = ?"]
        params: list[Any] = [portfolio_id]

        if asset_code:
            conditions.append("asset_code = ?")
            params.append(asset_code)
        if operation_type:
            conditions.append("operation_type = ?")
            params.append(operation_type)
        if start_date:
            conditions.append("operation_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("operation_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"""
            SELECT * FROM operations
            WHERE {where}
            ORDER BY operation_date DESC, id DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
