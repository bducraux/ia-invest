"""HTTP API for IA-Invest frontend integration.

This module exposes a FastAPI app that adapts existing repository/domain data
to the frontend contracts. It intentionally reuses the current storage and MCP
tool logic to keep business rules centralized.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.portfolios import get_portfolio_operations
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository

_DEFAULT_DB_PATH = Path(os.environ.get("IA_INVEST_DB", "ia_invest.db"))
_DEFAULT_CORS_ORIGINS = os.environ.get("IA_INVEST_API_CORS_ORIGINS", "http://localhost:3000")
_DEFAULT_QUOTES_ENABLED = os.environ.get("IA_INVEST_QUOTES_ENABLED", "1")
_DEFAULT_QUOTES_TTL_SECONDS = int(os.environ.get("IA_INVEST_QUOTES_TTL_SECONDS", "300"))
_DEFAULT_QUOTES_TIMEOUT_SECONDS = float(os.environ.get("IA_INVEST_QUOTES_TIMEOUT_SECONDS", "2.0"))


class PortfolioOut(BaseModel):
    id: str
    name: str
    currency: str = "BRL"


class AllocationSliceOut(BaseModel):
    assetClass: str
    label: str
    value: int
    weight: float


class PerformancePointOut(BaseModel):
    date: str
    value: int


class PortfolioSummaryOut(BaseModel):
    portfolioId: str
    totalInvested: int
    marketValue: int
    cashBalance: int
    unrealizedPnl: int
    unrealizedPnlPct: float
    monthDividends: int
    ytdReturnPct: float
    allocation: list[AllocationSliceOut]
    performance: list[PerformancePointOut]


class PositionOut(BaseModel):
    assetCode: str
    name: str
    assetClass: str
    quantity: float
    avgPrice: int
    marketPrice: int
    marketValue: int
    unrealizedPnl: int
    unrealizedPnlPct: float
    weight: float


class PositionsResponse(BaseModel):
    positions: list[PositionOut]


class OperationOut(BaseModel):
    id: str
    date: str
    assetCode: str
    type: str
    quantity: float
    unitPrice: int
    total: int
    source: str


class OperationsResponse(BaseModel):
    operations: list[OperationOut]
    total: int
    limit: int
    offset: int


def _to_ui_operation_type(operation_type: str) -> str:
    mapping = {
        "buy": "COMPRA",
        "sell": "VENDA",
        "dividend": "DIVIDENDO",
        "jcp": "JCP",
        "split": "DESDOBRAMENTO",
        "transfer_in": "COMPRA",
        "transfer_out": "VENDA",
    }
    return mapping.get(operation_type, operation_type.upper())


def _to_ui_asset_class(asset_type: str) -> str:
    mapping = {
        "stock": "ACAO",
        "fii": "FII",
        "etf": "ETF",
        "bond": "RENDA_FIXA",
        "crypto": "CRIPTO",
        "cash": "CAIXA",
    }
    return mapping.get(asset_type, "ACAO")


def _asset_class_label(asset_class: str) -> str:
    labels = {
        "ACAO": "Acoes",
        "FII": "FIIs",
        "ETF": "ETFs",
        "RENDA_FIXA": "Renda Fixa",
        "CRIPTO": "Cripto",
        "CAIXA": "Caixa",
    }
    return labels.get(asset_class, asset_class)


def _month_window(today: date) -> tuple[str, str]:
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    return start, end


def _build_performance_series(total_value_cents: int, months: int = 12) -> list[PerformancePointOut]:
    # V1 placeholder series: flat line by month using current portfolio value.
    today = date.today().replace(day=1)
    points: list[PerformancePointOut] = []
    for idx in range(months - 1, -1, -1):
        dt = today - relativedelta(months=idx)
        points.append(PerformancePointOut(date=dt.isoformat(), value=total_value_cents))
    return points


def _parse_bool_flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _count_operations(
    repo: OperationRepository,
    portfolio_id: str,
    *,
    asset_code: str | None,
    operation_type: str | None,
    start_date: str | None,
    end_date: str | None,
) -> int:
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
    row = repo._conn.execute(  # noqa: SLF001
        f"SELECT COUNT(1) AS total FROM operations WHERE {where}",
        params,
    ).fetchone()
    return int(row["total"]) if row else 0


def create_http_app(
    db_path: Path | str = _DEFAULT_DB_PATH,
    *,
    quotes_enabled: bool | None = None,
) -> FastAPI:
    app = FastAPI(title="IA-Invest HTTP API", version="0.1.0")
    origins = [origin.strip() for origin in _DEFAULT_CORS_ORIGINS.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db() -> Database:
        db = Database(db_path)
        db.initialize()
        return db

    def require_portfolio(portfolio_id: str, db: Database) -> None:
        repo = PortfolioRepository(db.connection)
        if repo.get(portfolio_id) is None:
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

    resolved_quotes_enabled = (
        _parse_bool_flag(_DEFAULT_QUOTES_ENABLED)
        if quotes_enabled is None
        else quotes_enabled
    )

    def build_quote_service(db: Database) -> MarketQuoteService:
        return MarketQuoteService(
            db.connection,
            enabled=resolved_quotes_enabled,
            ttl_seconds=_DEFAULT_QUOTES_TTL_SECONDS,
            timeout_seconds=_DEFAULT_QUOTES_TIMEOUT_SECONDS,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/portfolios", response_model=list[PortfolioOut])
    def list_portfolios(db: Database = Depends(get_db)) -> list[PortfolioOut]:  # noqa: B008
        repo = PortfolioRepository(db.connection)
        return [PortfolioOut(id=p.id, name=p.name, currency=p.base_currency) for p in repo.list_active()]

    @app.get("/api/portfolios/{portfolio_id}/operations", response_model=OperationsResponse)
    def list_operations(
        portfolio_id: str,
        assetCode: str | None = Query(default=None),
        operationType: str | None = Query(default=None),
        startDate: str | None = Query(default=None),
        endDate: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> OperationsResponse:
        require_portfolio(portfolio_id, db)

        internal_type_map = {
            "COMPRA": "buy",
            "VENDA": "sell",
            "DIVIDENDO": "dividend",
            "JCP": "jcp",
            "DESDOBRAMENTO": "split",
        }
        if operationType is None:
            op_type = None
        else:
            op_type = internal_type_map.get(operationType, operationType.lower())

        rows = get_portfolio_operations(
            db,
            portfolio_id,
            asset_code=assetCode,
            operation_type=op_type,
            start_date=startDate,
            end_date=endDate,
            limit=limit,
            offset=offset,
        )

        op_repo = OperationRepository(db.connection)
        total = _count_operations(
            op_repo,
            portfolio_id,
            asset_code=assetCode,
            operation_type=op_type,
            start_date=startDate,
            end_date=endDate,
        )

        mapped = [
            OperationOut(
                id=str(row["id"]),
                date=row["operation_date"],
                assetCode=row["asset_code"],
                type=_to_ui_operation_type(row["operation_type"]),
                quantity=float(row["quantity"]),
                unitPrice=int(row["unit_price"]),
                total=int(row["gross_value"]),
                source=row["source"],
            )
            for row in rows
        ]
        return OperationsResponse(operations=mapped, total=total, limit=limit, offset=offset)

    @app.get("/api/portfolios/{portfolio_id}/positions", response_model=PositionsResponse)
    def list_positions(
        portfolio_id: str,
        onlyOpen: bool = Query(default=True),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> PositionsResponse:
        require_portfolio(portfolio_id, db)

        pos_repo = PositionRepository(db.connection)
        rows = (
            pos_repo.list_open_by_portfolio(portfolio_id)
            if onlyOpen
            else pos_repo.list_by_portfolio(portfolio_id)
        )

        enriched: list[PositionOut] = []
        quote_service = build_quote_service(db)
        for row in rows:
            avg_price = int(row["avg_price"])
            market_price = quote_service.get_price_cents(row["asset_code"], row["asset_type"]) or avg_price
            market_value = int(round(float(row["quantity"]) * market_price))
            unrealized = market_value - int(row["total_cost"])
            unrealized_pct = (
                unrealized / int(row["total_cost"]) if int(row["total_cost"]) > 0 else 0.0
            )
            enriched.append(
                PositionOut(
                    assetCode=row["asset_code"],
                    name=row.get("asset_name") or row["asset_code"],
                    assetClass=_to_ui_asset_class(row["asset_type"]),
                    quantity=float(row["quantity"]),
                    avgPrice=avg_price,
                    marketPrice=market_price,
                    marketValue=market_value,
                    unrealizedPnl=unrealized,
                    unrealizedPnlPct=unrealized_pct,
                    weight=0.0,
                )
            )

        total_market = sum(p.marketValue for p in enriched)
        weighted = [
            p.model_copy(update={"weight": (p.marketValue / total_market) if total_market else 0.0})
            for p in enriched
        ]
        return PositionsResponse(positions=weighted)

    @app.get("/api/portfolios/{portfolio_id}/summary", response_model=PortfolioSummaryOut)
    def get_summary(
        portfolio_id: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> PortfolioSummaryOut:
        require_portfolio(portfolio_id, db)

        pos_repo = PositionRepository(db.connection)
        positions = pos_repo.list_open_by_portfolio(portfolio_id)
        quote_service = build_quote_service(db)

        total_invested = sum(int(row["total_cost"]) for row in positions)
        market_value = sum(
            int(
                round(
                    float(row["quantity"])
                    * (
                        quote_service.get_price_cents(row["asset_code"], row["asset_type"])
                        or int(row["avg_price"])
                    )
                )
            )
            for row in positions
        )
        unrealized = market_value - total_invested
        unrealized_pct = (unrealized / total_invested) if total_invested > 0 else 0.0

        start_month, end_month = _month_window(date.today())
        op_repo = OperationRepository(db.connection)
        dividend_ops = op_repo.list_all_by_portfolio(
            portfolio_id,
            operation_type="dividend",
            start_date=start_month,
            end_date=end_month,
        )
        jcp_ops = op_repo.list_all_by_portfolio(
            portfolio_id,
            operation_type="jcp",
            start_date=start_month,
            end_date=end_month,
        )
        month_dividends = sum(int(row["gross_value"]) for row in dividend_ops + jcp_ops)

        allocation_by_class: dict[str, int] = {}
        for row in positions:
            klass = _to_ui_asset_class(row["asset_type"])
            price_cents = quote_service.get_price_cents(row["asset_code"], row["asset_type"]) or int(
                row["avg_price"]
            )
            market_value_cents = int(round(float(row["quantity"]) * price_cents))
            allocation_by_class[klass] = allocation_by_class.get(klass, 0) + market_value_cents

        allocation_total = sum(allocation_by_class.values())
        allocation = [
            AllocationSliceOut(
                assetClass=klass,
                label=_asset_class_label(klass),
                value=value,
                weight=(value / allocation_total) if allocation_total else 0.0,
            )
            for klass, value in sorted(allocation_by_class.items())
        ]

        ytd_return_pct = (unrealized + month_dividends) / total_invested if total_invested > 0 else 0.0

        return PortfolioSummaryOut(
            portfolioId=portfolio_id,
            totalInvested=total_invested,
            marketValue=market_value,
            cashBalance=0,
            unrealizedPnl=unrealized,
            unrealizedPnlPct=unrealized_pct,
            monthDividends=month_dividends,
            ytdReturnPct=ytd_return_pct,
            allocation=allocation,
            performance=_build_performance_series(market_value),
        )

    return app


app = create_http_app()
