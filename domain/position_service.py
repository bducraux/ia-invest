"""Position service — deterministic position and P&L calculations.

All monetary values are integers in cents.  The service operates on a list of
already-persisted operations (as dicts from the repository) and produces a
list of Position objects ready for upsert.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from domain.models import Position

_BUY_TYPES = {"buy", "transfer_in", "split_bonus"}
_SELL_TYPES = {"sell", "transfer_out"}
_INCOME_TYPES = {"dividend", "jcp", "rendimento", "amortization"}


class PositionService:
    """Calculates current positions from a list of operation records.

    Usage::

        svc = PositionService()
        operations = op_repo.list_by_portfolio("renda-variavel")
        positions = svc.calculate(operations, portfolio_id="renda-variavel")
        pos_repo.upsert_many(positions)
    """

    def calculate(
        self, operations: list[dict[str, Any]], portfolio_id: str
    ) -> list[Position]:
        """Recalculate all positions from scratch for a portfolio.

        This method is idempotent — calling it multiple times with the same
        operations always produces the same result.
        """
        # Group operations by asset
        by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for op in operations:
            by_asset[op["asset_code"]].append(op)

        positions: list[Position] = []
        for asset_code, ops in by_asset.items():
            pos = self._calculate_asset_position(asset_code, ops, portfolio_id)
            positions.append(pos)

        return positions

    def _calculate_asset_position(
        self,
        asset_code: str,
        ops: list[dict[str, Any]],
        portfolio_id: str,
    ) -> Position:
        # Sort chronologically
        sorted_ops = sorted(ops, key=lambda o: (o["operation_date"], o["id"]))

        quantity = 0.0
        total_cost = 0           # cents
        realized_pnl = 0        # cents
        dividends = 0           # cents
        asset_type = sorted_ops[0]["asset_type"]
        asset_name: str | None = None

        for op in sorted_ops:
            op_type: str = op["operation_type"]
            qty: float = op["quantity"]
            gross: int = op["gross_value"]
            fees: int = op["fees"]

            if op.get("asset_name"):
                asset_name = op["asset_name"]

            if op_type in _BUY_TYPES:
                cost = gross + fees
                total_cost += cost
                quantity += qty

            elif op_type in _SELL_TYPES:
                if quantity > 0:
                    avg_cost_per_unit = total_cost / quantity
                    cost_sold = round(avg_cost_per_unit * qty)
                    proceeds = gross - fees
                    realized_pnl += proceeds - cost_sold
                    total_cost -= cost_sold
                quantity -= qty

            elif op_type in _INCOME_TYPES:
                dividends += gross - fees

        # Recalculate average price
        avg_price = round(total_cost / quantity) if quantity > 0 else 0

        first_date = sorted_ops[0]["operation_date"] if sorted_ops else None
        last_date = sorted_ops[-1]["operation_date"] if sorted_ops else None

        return Position(
            portfolio_id=portfolio_id,
            asset_code=asset_code,
            asset_type=asset_type,
            asset_name=asset_name,
            quantity=round(quantity, 8),
            avg_price=avg_price,
            total_cost=total_cost,
            realized_pnl=realized_pnl,
            dividends=dividends,
            first_operation_date=first_date,
            last_operation_date=last_date,
        )
