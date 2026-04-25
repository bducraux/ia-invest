"""MCP tool: ``get_concentration_analysis`` — risk concentration metrics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.concentration_service import ConcentrationService, ValuedAsset
from domain.position_valuation_service import PositionValuationService
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.positions_with_quote import _row_to_position
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_concentration_analysis(
    db: Database,
    portfolio_id: str,
    *,
    quote_service: MarketQuoteService | None = None,
) -> dict[str, Any]:
    """Return concentration metrics + alerts for ``portfolio_id``.

    Positions without a market quote fall back to their stored cost basis
    (``total_cost_cents``) so the analysis still surfaces — this is
    documented in ``valuation_method`` per asset so the consumer can warn
    when the picture is partially synthetic.
    """
    portfolio_repo = PortfolioRepository(db.connection)
    if portfolio_repo.get(portfolio_id) is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    pos_repo = PositionRepository(db.connection)
    valuator = PositionValuationService()
    service = quote_service or MarketQuoteService(db.connection, enabled=False)

    valued_assets: list[ValuedAsset] = []
    used_cost_fallback: list[str] = []

    for row in pos_repo.list_by_portfolio(portfolio_id):
        position = _row_to_position(dict(row), portfolio_id)
        if position.quantity <= 0:
            continue
        quote = service.resolve_price(position.asset_code, position.asset_type)
        valued = valuator.value(position, quote)
        if valued.current_value_cents is not None:
            value_cents = valued.current_value_cents
        elif valued.total_cost_cents > 0:
            value_cents = valued.total_cost_cents
            used_cost_fallback.append(valued.asset_code)
        else:
            continue
        if value_cents <= 0:
            continue
        valued_assets.append(
            ValuedAsset(asset_code=valued.asset_code, value_cents=value_cents)
        )

    payload = ConcentrationService().analyse(valued_assets)
    payload["portfolio_id"] = portfolio_id
    payload["as_of"] = _utc_now_iso()
    if used_cost_fallback:
        payload["valuation_warnings"] = {
            "code": "cost_basis_fallback",
            "message": (
                "Sem cotação atual para os ativos abaixo; valor calculado a partir "
                "do custo médio."
            ),
            "assets": sorted(used_cost_fallback),
        }
    return payload


__all__ = ["get_concentration_analysis"]
