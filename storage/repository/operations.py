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
                        broker, account, notes, raw_data_json
                    ) VALUES (
                        :portfolio_id, :import_job_id, :source, :external_id,
                        :asset_code, :asset_type, :asset_name,
                        :operation_type, :operation_date, :settlement_date,
                        :quantity, :unit_price, :gross_value, :fees, :net_value,
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
