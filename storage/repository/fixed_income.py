"""Repository for fixed-income (renda fixa) positions."""

from __future__ import annotations

import sqlite3
from typing import Any

from domain.fixed_income import FixedIncomePosition


class FixedIncomePositionRepository:
    """CRUD operations for the ``fixed_income_positions`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Inserts
    # ------------------------------------------------------------------

    def insert(self, position: FixedIncomePosition, *, commit: bool = True) -> int:
        """Insert a single position. Returns the new row id."""
        new_id = self._insert_execute(position)
        if commit:
            self._conn.commit()
        return new_id

    def insert_many(self, positions: list[FixedIncomePosition]) -> int:
        """Insert several positions in a single transaction. Returns the number inserted."""
        for p in positions:
            self._insert_execute(p)
        self._conn.commit()
        return len(positions)

    def update(self, position: FixedIncomePosition, *, commit: bool = True) -> None:
        """Update an existing fixed-income position by id."""
        if position.id is None:
            raise ValueError("position.id is required for update")

        self._conn.execute(
            """
            UPDATE fixed_income_positions
            SET institution = :institution,
                asset_type = :asset_type,
                product_name = :product_name,
                remuneration_type = :remuneration_type,
                benchmark = :benchmark,
                investor_type = :investor_type,
                currency = :currency,
                application_date = :application_date,
                maturity_date = :maturity_date,
                liquidity_label = :liquidity_label,
                principal_applied_brl = :principal_applied_brl,
                fixed_rate_annual_percent = :fixed_rate_annual_percent,
                benchmark_percent = :benchmark_percent,
                notes = :notes,
                status = :status,
                auto_reapply_enabled = :auto_reapply_enabled,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = :id
              AND portfolio_id = :portfolio_id
            """,
            {
                **self._to_params(position),
                "id": position.id,
            },
        )
        if commit:
            self._conn.commit()

    def set_auto_reapply(
        self,
        position_id: int,
        portfolio_id: str,
        enabled: bool,
        *,
        commit: bool = True,
    ) -> None:
        self._conn.execute(
            """
            UPDATE fixed_income_positions
            SET auto_reapply_enabled = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ?
              AND portfolio_id = ?
            """,
            (1 if enabled else 0, position_id, portfolio_id),
        )
        if commit:
            self._conn.commit()

    def mark_matured_if_due(
        self,
        portfolio_id: str,
        as_of_date: str,
        *,
        commit: bool = True,
    ) -> int:
        cur = self._conn.execute(
            """
            UPDATE fixed_income_positions
            SET status = 'MATURED',
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE portfolio_id = ?
              AND status = 'ACTIVE'
              AND maturity_date <= ?
            """,
            (portfolio_id, as_of_date),
        )
        if commit:
            self._conn.commit()
        return int(cur.rowcount or 0)

    def list_auto_reapply_candidates(
        self,
        portfolio_id: str,
        *,
        as_of_date: str,
    ) -> list[FixedIncomePosition]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM fixed_income_positions
            WHERE portfolio_id = ?
              AND auto_reapply_enabled = 1
              AND maturity_date <= ?
            ORDER BY maturity_date ASC, id ASC
            """,
            (portfolio_id, as_of_date),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def delete(
        self,
        position_id: int,
        portfolio_id: str,
        *,
        commit: bool = True,
    ) -> None:
        """Delete a position by id. No-op if the row does not exist."""
        self._conn.execute(
            "DELETE FROM fixed_income_positions WHERE id = ? AND portfolio_id = ?",
            (position_id, portfolio_id),
        )
        if commit:
            self._conn.commit()

    def _insert_execute(self, position: FixedIncomePosition) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO fixed_income_positions (
                portfolio_id, import_job_id, external_id,
                institution, asset_type, product_name,
                remuneration_type, benchmark, investor_type, currency,
                application_date, maturity_date, liquidity_label,
                principal_applied_brl, fixed_rate_annual_percent, benchmark_percent,
                notes,
                status,
                auto_reapply_enabled
            ) VALUES (
                :portfolio_id, :import_job_id, :external_id,
                :institution, :asset_type, :product_name,
                :remuneration_type, :benchmark, :investor_type, :currency,
                :application_date, :maturity_date, :liquidity_label,
                :principal_applied_brl, :fixed_rate_annual_percent, :benchmark_percent,
                :notes,
                :status,
                :auto_reapply_enabled
            )
            """,
            self._to_params(position),
        )
        new_id = int(cur.lastrowid or 0)
        position.id = new_id
        return new_id

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, position_id: int) -> FixedIncomePosition | None:
        row = self._conn.execute(
            "SELECT * FROM fixed_income_positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        status: str | None = None,
    ) -> list[FixedIncomePosition]:
        params: list[Any] = [portfolio_id]
        sql = "SELECT * FROM fixed_income_positions WHERE portfolio_id = ?"
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY application_date DESC, id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_params(position: FixedIncomePosition) -> dict[str, Any]:
        return {
            "portfolio_id": position.portfolio_id,
            "import_job_id": position.import_job_id,
            "external_id": position.external_id,
            "institution": position.institution,
            "asset_type": position.asset_type,
            "product_name": position.product_name,
            "remuneration_type": position.remuneration_type,
            "benchmark": position.benchmark,
            "investor_type": position.investor_type,
            "currency": position.currency,
            "application_date": position.application_date,
            "maturity_date": position.maturity_date,
            "liquidity_label": position.liquidity_label,
            "principal_applied_brl": position.principal_applied_brl,
            "fixed_rate_annual_percent": position.fixed_rate_annual_percent,
            "benchmark_percent": position.benchmark_percent,
            "notes": position.notes,
            "status": position.status,
            "auto_reapply_enabled": 1 if position.auto_reapply_enabled else 0,
        }

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> FixedIncomePosition:
        return FixedIncomePosition(
            id=int(row["id"]),
            portfolio_id=row["portfolio_id"],
            import_job_id=row["import_job_id"],
            external_id=row["external_id"],
            institution=row["institution"],
            asset_type=row["asset_type"],
            product_name=row["product_name"],
            remuneration_type=row["remuneration_type"],
            benchmark=row["benchmark"],
            investor_type=row["investor_type"],
            currency=row["currency"],
            application_date=row["application_date"],
            maturity_date=row["maturity_date"],
            liquidity_label=row["liquidity_label"],
            principal_applied_brl=int(row["principal_applied_brl"]),
            fixed_rate_annual_percent=(
                float(row["fixed_rate_annual_percent"])
                if row["fixed_rate_annual_percent"] is not None
                else None
            ),
            benchmark_percent=(
                float(row["benchmark_percent"])
                if row["benchmark_percent"] is not None
                else None
            ),
            notes=row["notes"],
            status=row["status"],
            auto_reapply_enabled=bool(row["auto_reapply_enabled"]),
        )
