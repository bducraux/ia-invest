"""Lifecycle transitions for event-sourced positions and operations.

Covers renda variavel, cripto, internacional and any other portfolio that
relies on the ``operations`` ledger as the source of truth (i.e. positions
are computed by :class:`domain.position_service.PositionService`).

Three actions are supported:

close_position(portfolio_id, asset_code)
    Delete every operation of the asset in the portfolio plus the row in
    ``positions``. Non-reversible.

delete_operation(portfolio_id, operation_id)
    Delete a single operation and recompute the affected asset's position
    (or remove the position row when no operations remain).

update_operation(portfolio_id, operation_id, fields)
    Patch whitelisted fields of an operation and recompute affected
    positions. When ``asset_code`` changes, both the old and the new asset
    are recomputed.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from domain.models import Operation
from domain.position_service import PositionService
from storage.repository.operations import OperationRepository
from storage.repository.positions import PositionRepository


class PositionLifecycleService:
    """Encapsulates position/operation lifecycle actions."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        operation_repo: OperationRepository,
        position_repo: PositionRepository,
        position_service: PositionService,
    ) -> None:
        self._conn = conn
        self._op_repo = operation_repo
        self._pos_repo = position_repo
        self._svc = position_service

    # ------------------------------------------------------------------
    # Create operation — manual entry; recompute affected asset
    # ------------------------------------------------------------------

    def create_operation(
        self,
        portfolio_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert a single manually-entered operation and recompute the asset.

        Required fields: ``asset_code``, ``asset_type``, ``operation_type``,
        ``operation_date``, ``quantity``, ``unit_price`` (cents),
        ``gross_value`` (cents). Optional: ``fees`` (cents), ``net_value``
        (cents — auto-derived when omitted), ``settlement_date``,
        ``asset_name``, ``broker``, ``account``, ``notes``.

        Returns the persisted operation row. Raises ``ValueError`` on
        duplicate (UNIQUE constraint).
        """
        required = (
            "asset_code",
            "asset_type",
            "operation_type",
            "operation_date",
            "quantity",
            "unit_price",
            "gross_value",
        )
        for key in required:
            if fields.get(key) in (None, ""):
                raise ValueError(f"Missing required field: {key}")

        external_id = fields.get("external_id")
        if not external_id:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM operations",
            ).fetchone()
            external_id = f"manual:created:{int(row['next_id'])}"

        op = Operation(
            portfolio_id=portfolio_id,
            source=fields.get("source") or "manual",
            external_id=external_id,
            asset_code=str(fields["asset_code"]).upper(),
            asset_type=str(fields["asset_type"]).upper(),
            asset_name=fields.get("asset_name"),
            operation_type=str(fields["operation_type"]),
            operation_date=str(fields["operation_date"]),
            settlement_date=fields.get("settlement_date"),
            quantity=float(fields["quantity"]),
            unit_price=int(fields["unit_price"]),
            gross_value=int(fields["gross_value"]),
            fees=int(fields.get("fees") or 0),
            net_value=int(fields.get("net_value") or 0),
            broker=fields.get("broker"),
            account=fields.get("account"),
            notes=fields.get("notes"),
        )

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            try:
                cursor = self._conn.execute(
                    """
                    INSERT INTO operations (
                        portfolio_id, source, external_id,
                        asset_code, asset_type, asset_name,
                        operation_type, operation_date, settlement_date,
                        quantity, unit_price, gross_value, fees, net_value,
                        trade_currency, unit_price_native, gross_value_native,
                        fees_native, fx_rate_at_trade, fx_rate_source,
                        broker, account, notes
                    ) VALUES (
                        :portfolio_id, :source, :external_id,
                        :asset_code, :asset_type, :asset_name,
                        :operation_type, :operation_date, :settlement_date,
                        :quantity, :unit_price, :gross_value, :fees, :net_value,
                        :trade_currency, :unit_price_native, :gross_value_native,
                        :fees_native, :fx_rate_at_trade, :fx_rate_source,
                        :broker, :account, :notes
                    )
                    """,
                    {
                        "portfolio_id": op.portfolio_id,
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
                    },
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Duplicate operation (matches an existing entry)."
                ) from exc
            new_id = cursor.lastrowid
            self._recompute_assets(portfolio_id, [op.asset_code])
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

        new_row = self._conn.execute(
            "SELECT * FROM operations WHERE id = ?",
            (new_id,),
        ).fetchone()
        if new_row is None:  # pragma: no cover - defensive
            raise ValueError("Failed to retrieve created operation")
        return dict(new_row)

    # ------------------------------------------------------------------
    # Close position — delete all operations + positions row
    # ------------------------------------------------------------------

    def close_position(self, portfolio_id: str, asset_code: str) -> int:
        """Delete every operation for ``asset_code`` plus its positions row.

        Returns the number of operations that were deleted.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            deleted_ops = self._op_repo.delete_by_asset(
                portfolio_id, asset_code, commit=False
            )
            self._pos_repo.delete(portfolio_id, asset_code, commit=False)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return deleted_ops

    # ------------------------------------------------------------------
    # Delete operation — recompute affected asset
    # ------------------------------------------------------------------

    def delete_operation(self, portfolio_id: str, operation_id: int) -> str:
        """Delete a single operation. Returns the affected ``asset_code``.

        Raises ``ValueError("Operation not found")`` if the row does not
        exist or does not belong to the portfolio.
        """
        op = self._op_repo.get(operation_id)
        if op is None or op["portfolio_id"] != portfolio_id:
            raise ValueError("Operation not found")
        asset_code = op["asset_code"]

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._op_repo.delete(operation_id, portfolio_id, commit=False)
            self._recompute_assets(portfolio_id, [asset_code])
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return asset_code

    # ------------------------------------------------------------------
    # Update operation — recompute old + new asset_code
    # ------------------------------------------------------------------

    def update_operation(
        self,
        portfolio_id: str,
        operation_id: int,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Patch whitelisted fields and recompute affected positions.

        Returns the persisted operation row.
        """
        current = self._op_repo.get(operation_id)
        if current is None or current["portfolio_id"] != portfolio_id:
            raise ValueError("Operation not found")

        affected: set[str] = {current["asset_code"]}
        new_asset_code = fields.get("asset_code")
        if new_asset_code is not None:
            affected.add(new_asset_code)

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._op_repo.update(
                operation_id, portfolio_id, fields, commit=False
            )
            self._recompute_assets(portfolio_id, sorted(affected))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

        persisted = self._op_repo.get(operation_id)
        if persisted is None:  # pragma: no cover - defensive
            raise ValueError("Operation not found")
        return persisted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _recompute_assets(
        self, portfolio_id: str, asset_codes: list[str]
    ) -> None:
        """Recompute positions for the given asset codes.

        For each asset: if any operation remains, recompute and upsert.
        Otherwise, drop the orphan positions row.
        """
        all_ops = self._op_repo.list_all_by_portfolio(portfolio_id)
        ops_by_asset: dict[str, list[dict[str, Any]]] = {}
        for op in all_ops:
            ops_by_asset.setdefault(op["asset_code"], []).append(op)

        for asset_code in asset_codes:
            asset_ops = ops_by_asset.get(asset_code)
            if not asset_ops:
                self._pos_repo.delete(portfolio_id, asset_code, commit=False)
                continue
            positions = self._svc.calculate(asset_ops, portfolio_id)
            for pos in positions:
                # Inline upsert without per-row commit to stay within tx.
                self._pos_repo._upsert_execute(pos)  # noqa: SLF001
