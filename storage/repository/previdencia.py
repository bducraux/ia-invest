"""Repository for previdencia snapshots."""

from __future__ import annotations

import sqlite3

from domain.previdencia import PrevidenciaSnapshot


class PrevidenciaSnapshotRepository:
    """CRUD operations for previdencia_snapshots with temporal guard."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_asset(self, portfolio_id: str, asset_code: str) -> PrevidenciaSnapshot | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM previdencia_snapshots
            WHERE portfolio_id = ? AND asset_code = ?
            """,
            (portfolio_id, asset_code),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list_by_portfolio(self, portfolio_id: str) -> list[PrevidenciaSnapshot]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM previdencia_snapshots
            WHERE portfolio_id = ?
            ORDER BY asset_code ASC
            """,
            (portfolio_id,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def upsert_if_newer(self, snapshot: PrevidenciaSnapshot) -> str:
        """Upsert a snapshot when period_month is not older than current row.

        Returns one of: "inserted", "updated", "skipped_older".
        """
        current = self.get_by_asset(snapshot.portfolio_id, snapshot.asset_code)
        if current is None:
            self._insert(snapshot)
            return "inserted"

        if snapshot.period_month < current.period_month:
            return "skipped_older"

        self._conn.execute(
            """
            UPDATE previdencia_snapshots
            SET product_name = :product_name,
                quantity = :quantity,
                unit_price_cents = :unit_price_cents,
                market_value_cents = :market_value_cents,
                period_month = :period_month,
                period_start_date = :period_start_date,
                period_end_date = :period_end_date,
                source_file = :source_file,
                import_job_id = :import_job_id,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE portfolio_id = :portfolio_id
              AND asset_code = :asset_code
            """,
            self._to_params(snapshot),
        )
        self._conn.commit()
        return "updated"

    def _insert(self, snapshot: PrevidenciaSnapshot) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO previdencia_snapshots (
                portfolio_id,
                asset_code,
                product_name,
                quantity,
                unit_price_cents,
                market_value_cents,
                period_month,
                period_start_date,
                period_end_date,
                source_file,
                import_job_id
            ) VALUES (
                :portfolio_id,
                :asset_code,
                :product_name,
                :quantity,
                :unit_price_cents,
                :market_value_cents,
                :period_month,
                :period_start_date,
                :period_end_date,
                :source_file,
                :import_job_id
            )
            """,
            self._to_params(snapshot),
        )
        self._conn.commit()
        snapshot.id = int(cur.lastrowid or 0)
        return int(cur.lastrowid or 0)

    # Whitelist of editable snapshot fields.
    _UPDATABLE_FIELDS: tuple[str, ...] = (
        "product_name",
        "quantity",
        "unit_price_cents",
        "market_value_cents",
        "period_month",
        "period_start_date",
        "period_end_date",
    )

    def update(
        self,
        portfolio_id: str,
        asset_code: str,
        fields: dict[str, object],
    ) -> int:
        unknown = set(fields) - set(self._UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"Cannot update fields: {sorted(unknown)}")
        if not fields:
            return 0
        assignments = ", ".join(f"{col} = :{col}" for col in fields)
        params: dict[str, object] = dict(fields)
        params["portfolio_id"] = portfolio_id
        params["asset_code"] = asset_code
        cur = self._conn.execute(
            f"""
            UPDATE previdencia_snapshots
            SET {assignments},
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE portfolio_id = :portfolio_id AND asset_code = :asset_code
            """,
            params,
        )
        self._conn.commit()
        return cur.rowcount

    def delete(self, portfolio_id: str, asset_code: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM previdencia_snapshots WHERE portfolio_id = ? AND asset_code = ?",
            (portfolio_id, asset_code),
        )
        self._conn.commit()
        return cur.rowcount

    @staticmethod
    def _to_params(snapshot: PrevidenciaSnapshot) -> dict[str, object]:
        return {
            "portfolio_id": snapshot.portfolio_id,
            "asset_code": snapshot.asset_code,
            "product_name": snapshot.product_name,
            "quantity": snapshot.quantity,
            "unit_price_cents": snapshot.unit_price_cents,
            "market_value_cents": snapshot.market_value_cents,
            "period_month": snapshot.period_month,
            "period_start_date": snapshot.period_start_date,
            "period_end_date": snapshot.period_end_date,
            "source_file": snapshot.source_file,
            "import_job_id": snapshot.import_job_id,
        }

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PrevidenciaSnapshot:
        return PrevidenciaSnapshot(
            id=int(row["id"]),
            portfolio_id=row["portfolio_id"],
            asset_code=row["asset_code"],
            product_name=row["product_name"],
            quantity=float(row["quantity"]),
            unit_price_cents=int(row["unit_price_cents"]),
            market_value_cents=int(row["market_value_cents"]),
            period_month=row["period_month"],
            period_start_date=row["period_start_date"],
            period_end_date=row["period_end_date"],
            source_file=row["source_file"],
            import_job_id=row["import_job_id"],
        )
