"""MCP tool — write-side: add manual buy/sell (and other) operations.

This is the only write-side tool besides ``transfer_portfolio_owner``. It lets
the agent record one or more operations in a single atomic batch, recomputing
positions once at the end.

Portfolio resolution:
    * ``portfolio_id`` (namespaced ``<owner>__<slug>``) wins when provided.
    * Otherwise ``member_id`` and/or ``portfolio_type`` (slug, e.g. "renda-variavel")
      are used to look up a unique candidate. When ambiguous, the tool returns a
      structured error listing the candidates so the agent can ask the user.

Per-operation input convention:
    * ``unit_price_brl`` is a decimal in BRL (e.g. 3.57). Internally converted
      to integer cents.
    * ``operation_date`` is required (ISO 8601). The agent must ask the user
      when missing — there is no implicit "today" default.
    * ``operation_type`` defaults to "buy".
    * ``asset_type`` is inferred from ``asset_code`` when omitted.
"""

from __future__ import annotations

from typing import Any

from domain.position_service import PositionService
from mcp_server.services.position_lifecycle import PositionLifecycleService
from normalizers.validator import (
    infer_asset_type,
    normalise_asset_code,
    normalise_operation_type,
    parse_date,
    parse_quantity,
)
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _resolve_portfolio(
    db: Database,
    *,
    portfolio_id: str | None,
    member_id: str | None,
    portfolio_type: str | None,
) -> dict[str, Any]:
    """Resolve a unique active portfolio from the args.

    Returns ``{"portfolio_id": str}`` on success, or
    ``{"error": str, "candidates": [...]}`` when ambiguous / missing.
    """
    portfolio_repo = PortfolioRepository(db.connection)

    if portfolio_id:
        portfolio = portfolio_repo.get(portfolio_id)
        if portfolio is None:
            return {"error": f"Portfolio '{portfolio_id}' not found."}
        if portfolio.status != "active":
            return {"error": f"Portfolio '{portfolio_id}' is not active."}
        return {"portfolio_id": portfolio.id}

    member_repo = MemberRepository(db.connection)
    resolved_member = None
    if member_id:
        resolved_member = member_repo.get(member_id) or member_repo.get_by_id_or_name(
            member_id
        )
        if resolved_member is None:
            return {"error": f"Member '{member_id}' not found."}

    candidates = []
    if resolved_member is not None and portfolio_type:
        portfolios = [
            p
            for p in portfolio_repo.list_by_owner(resolved_member.id, only_active=True)
            if p.slug == portfolio_type
        ]
        candidates = portfolios
    elif resolved_member is not None:
        candidates = portfolio_repo.list_by_owner(resolved_member.id, only_active=True)
    elif portfolio_type:
        candidates = [p for p in portfolio_repo.list_active() if p.slug == portfolio_type]
    else:
        return {
            "error": (
                "Specify portfolio_id, or (member_id and/or portfolio_type) to "
                "resolve a unique portfolio."
            )
        }

    if not candidates:
        scope = []
        if resolved_member is not None:
            scope.append(f"member='{resolved_member.id}'")
        if portfolio_type:
            scope.append(f"portfolio_type='{portfolio_type}'")
        return {"error": f"No active portfolio matches {', '.join(scope)}."}

    if len(candidates) == 1:
        return {"portfolio_id": candidates[0].id}

    return {
        "error": (
            "Multiple active portfolios match. Ask the user which one and pass "
            "portfolio_id explicitly."
        ),
        "candidates": [
            {
                "portfolio_id": p.id,
                "owner_id": p.owner_id,
                "slug": p.slug,
                "name": p.name,
            }
            for p in candidates
        ],
    }


def _normalise_entry(index: int, entry: dict[str, Any]) -> dict[str, Any]:
    """Convert a user-friendly entry dict into the snake_case fields dict
    expected by ``PositionLifecycleService.create_operations``.

    Raises ``ValueError`` with a 1-indexed prefix on validation failure.
    """
    prefix = f"Entry #{index + 1}"

    asset_code_raw = entry.get("asset_code")
    if not asset_code_raw:
        raise ValueError(f"{prefix}: 'asset_code' is required.")
    asset_code = normalise_asset_code(asset_code_raw)

    quantity_raw = entry.get("quantity")
    if quantity_raw is None or quantity_raw == "":
        raise ValueError(f"{prefix}: 'quantity' is required.")
    quantity = parse_quantity(quantity_raw)
    if quantity == 0:
        raise ValueError(f"{prefix}: 'quantity' must be greater than zero.")

    if "unit_price_brl" not in entry and "unit_price_cents" not in entry:
        raise ValueError(f"{prefix}: 'unit_price_brl' is required.")
    if "unit_price_cents" in entry and entry["unit_price_cents"] is not None:
        unit_price_cents = int(entry["unit_price_cents"])
    else:
        try:
            unit_price_brl = float(entry["unit_price_brl"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{prefix}: 'unit_price_brl' must be a number (BRL, e.g. 3.57)."
            ) from exc
        if unit_price_brl < 0:
            raise ValueError(f"{prefix}: 'unit_price_brl' must be non-negative.")
        unit_price_cents = round(unit_price_brl * 100)

    operation_date_raw = entry.get("operation_date")
    if not operation_date_raw:
        raise ValueError(
            f"{prefix}: 'operation_date' is required (ISO 8601 YYYY-MM-DD)."
        )
    operation_date = parse_date(str(operation_date_raw))

    operation_type = normalise_operation_type(entry.get("operation_type") or "buy")

    asset_type = entry.get("asset_type")
    if not asset_type:
        asset_type = infer_asset_type(asset_code)

    fees_cents = 0
    if entry.get("fees_brl") is not None:
        try:
            fees_brl = float(entry["fees_brl"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{prefix}: 'fees_brl' must be a number.") from exc
        if fees_brl < 0:
            raise ValueError(f"{prefix}: 'fees_brl' must be non-negative.")
        fees_cents = round(fees_brl * 100)
    elif entry.get("fees_cents") is not None:
        fees_cents = int(entry["fees_cents"])

    gross_value = round(quantity * unit_price_cents)

    fields: dict[str, Any] = {
        "asset_code": asset_code,
        "asset_type": asset_type,
        "operation_type": operation_type,
        "operation_date": operation_date,
        "quantity": quantity,
        "unit_price": unit_price_cents,
        "gross_value": gross_value,
        "fees": fees_cents,
    }
    for optional in ("asset_name", "broker", "account", "notes", "settlement_date"):
        value = entry.get(optional)
        if value not in (None, ""):
            fields[optional] = value
    return fields


def add_operations(
    db: Database,
    *,
    portfolio_id: str | None = None,
    member_id: str | None = None,
    portfolio_type: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record one or more operations in a portfolio (atomic batch).

    See module docstring for the resolution and validation rules.
    """
    if not operations:
        return {"error": "'operations' must contain at least one entry."}

    resolution = _resolve_portfolio(
        db,
        portfolio_id=portfolio_id,
        member_id=member_id,
        portfolio_type=portfolio_type,
    )
    if "error" in resolution:
        return resolution

    resolved_id = resolution["portfolio_id"]

    try:
        prepared = [_normalise_entry(i, entry) for i, entry in enumerate(operations)]
    except ValueError as exc:
        return {"error": str(exc), "inserted": []}

    lifecycle = PositionLifecycleService(
        db.connection,
        OperationRepository(db.connection),
        PositionRepository(db.connection),
        PositionService(),
    )
    try:
        result = lifecycle.create_operations(resolved_id, prepared)
    except ValueError as exc:
        return {"error": str(exc), "inserted": []}

    inserted = result["inserted"]
    affected = result["affected_assets"]

    total_gross = sum(int(r.get("gross_value") or 0) for r in inserted)
    total_fees = sum(int(r.get("fees") or 0) for r in inserted)

    return {
        "portfolio_id": resolved_id,
        "inserted": [
            {
                "id": r["id"],
                "asset_code": r["asset_code"],
                "operation_type": r["operation_type"],
                "operation_date": r["operation_date"],
                "quantity": r["quantity"],
                "unit_price_cents": r["unit_price"],
                "gross_value_cents": r["gross_value"],
                "fees_cents": r["fees"],
            }
            for r in inserted
        ],
        "summary": {
            "count_inserted": len(inserted),
            "affected_assets": affected,
            "total_gross_value_cents": total_gross,
            "total_fees_cents": total_fees,
        },
    }
