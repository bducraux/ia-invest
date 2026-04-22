"""HTTP API for IA-Invest frontend integration.

This module exposes a FastAPI app that adapts existing repository/domain data
to the frontend contracts. It intentionally reuses the current storage and MCP
tool logic to keep business rules centralized.
"""

from __future__ import annotations

import math
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import FlatCDIRateProvider
from domain.fixed_income_valuation import FixedIncomeValuationService
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.portfolios import get_portfolio_operations
from normalizers.fixed_income_csv import FixedIncomeCSVImporter
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository
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


class PortfolioUpdate(BaseModel):
    name: str


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
    previdenciaTotalValue: int
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
    quoteStatus: str
    quoteSource: str
    quoteAgeSeconds: int | None = None


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


class QuoteRefreshResponse(BaseModel):
    scope: str
    portfolios: list[str]
    totalAssets: int
    liveCount: int
    cacheFreshCount: int
    cacheStaleCount: int
    avgFallbackCount: int
    failedCount: int


class AppSettingsOut(BaseModel):
    cdiAnnualRate: float | None = None
    selicAnnualRate: float | None = None
    ipcaAnnualRate: float | None = None


class AppSettingsUpdate(BaseModel):
    cdiAnnualRate: float | None = None
    selicAnnualRate: float | None = None
    ipcaAnnualRate: float | None = None


# --- Fixed-income (renda fixa) -----------------------------------------------


class FixedIncomePositionCreate(BaseModel):
    institution: str
    assetType: str               # CDB | LCI | LCA
    productName: str
    remunerationType: str        # PRE | CDI_PERCENT
    benchmark: str | None = None
    applicationDate: str
    maturityDate: str
    principalAppliedBrl: int     # cents
    fixedRateAnnualPercent: float | None = None
    benchmarkPercent: float | None = None
    liquidityLabel: str | None = None
    notes: str | None = None


class FixedIncomePositionOut(BaseModel):
    id: int
    institution: str
    assetType: str
    productName: str
    remunerationType: str
    benchmark: str
    investorType: str
    currency: str
    applicationDate: str
    maturityDate: str
    liquidityLabel: str | None = None
    principalAppliedBrl: int
    fixedRateAnnualPercent: float | None = None
    benchmarkPercent: float | None = None
    grossValueCurrentBrl: int
    grossIncomeCurrentBrl: int
    estimatedIrCurrentBrl: int
    netValueCurrentBrl: int
    taxBracketCurrent: str | None = None
    daysSinceApplication: int
    valuationDate: str
    isComplete: bool
    incompleteReason: str | None = None
    status: str
    importedGrossValueBrl: int | None = None
    importedNetValueBrl: int | None = None
    importedEstimatedIrBrl: int | None = None
    grossDiffBrl: int | None = None
    netDiffBrl: int | None = None
    notes: str | None = None


class FixedIncomePositionsResponse(BaseModel):
    positions: list[FixedIncomePositionOut]


class FixedIncomeImportError(BaseModel):
    rowIndex: int | None = None
    message: str
    field: str | None = None


class FixedIncomeImportResponse(BaseModel):
    imported: int
    failed: int
    positions: list[FixedIncomePositionOut]
    errors: list[FixedIncomeImportError]


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
        "previdencia": "PREVIDENCIA",
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
        "PREVIDENCIA": "Previdencia",
        "CRIPTO": "Cripto",
        "CAIXA": "Caixa",
    }
    return labels.get(asset_class, asset_class)


def _format_percent(value: float | None) -> str | None:
    if value is None:
        return None
    rendered = f"{value:.4f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _fixed_income_display_name(position: FixedIncomePosition) -> str:
    """Build a human-friendly label for fixed-income assets."""
    institution = position.institution.strip()
    product = position.product_name.strip()
    asset_type = position.asset_type.strip().upper()

    if product:
        return f"{asset_type} {institution} {product}".strip()

    if position.remuneration_type == "CDI_PERCENT":
        pct = _format_percent(position.benchmark_percent)
        if pct is not None:
            return f"{asset_type} {institution} {pct}% CDI".strip()

    if position.remuneration_type == "PRE":
        rate = _format_percent(position.fixed_rate_annual_percent)
        if rate is not None:
            return f"{asset_type} {institution} {rate}% a.a.".strip()

    return f"{asset_type} {institution}".strip()


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


def _build_fixed_income_valuation_service(db: Database) -> FixedIncomeValuationService:
    """Build valuation service with optional CDI provider.

    Rates are stored as percentages (e.g. 14.65 means 14.65% a.a.).
    Converts annual percent to daily fraction: daily = (1 + rate/100)^(1/252) - 1

    Priority:
    1) Persisted SQLite app setting (app_settings key=cdi_annual_rate)
    2) IA_INVEST_CDI_DAILY_RATE environment variable (legacy daily rate fraction)
    """
    # Try to get annual CDI rate from database (stored as percent, e.g. 14.65)
    row = db.connection.execute(
        "SELECT value FROM app_settings WHERE key = 'cdi_annual_rate'"
    ).fetchone()
    configured_annual_rate = row["value"] if row is not None else None

    if configured_annual_rate:
        try:
            annual_pct = float(configured_annual_rate.strip())
            if annual_pct > 0 and math.isfinite(annual_pct):
                # Stored as percentage → convert to fraction first, then to daily:
                # daily = (1 + annual_pct/100)^(1/252) - 1
                daily_rate = math.pow(1 + annual_pct / 100, 1 / 252) - 1
                provider = FlatCDIRateProvider(Decimal(str(daily_rate)))
                return FixedIncomeValuationService(cdi_provider=provider)
        except Exception as exc:  # noqa: BLE001
            _ = exc
    
    # Fallback to legacy environment variable (daily rate)
    configured_daily_rate = os.environ.get("IA_INVEST_CDI_DAILY_RATE")
    if configured_daily_rate is None or configured_daily_rate.strip() == "":
        return FixedIncomeValuationService()

    try:
        provider = FlatCDIRateProvider(Decimal(configured_daily_rate.strip()))
    except Exception as exc:  # noqa: BLE001
        # Keep API functional if runtime config is malformed.
        _ = exc
        return FixedIncomeValuationService()

    return FixedIncomeValuationService(cdi_provider=provider)


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

    def build_quote_service(db: Database, *, force_live: bool = False) -> MarketQuoteService:
        return MarketQuoteService(
            db.connection,
            enabled=(resolved_quotes_enabled or force_live),
            ttl_seconds=_DEFAULT_QUOTES_TTL_SECONDS,
            timeout_seconds=_DEFAULT_QUOTES_TIMEOUT_SECONDS,
        )

    def refresh_quotes_for_portfolios(
        db: Database,
        portfolio_ids: list[str],
    ) -> QuoteRefreshResponse:
        pos_repo = PositionRepository(db.connection)
        quote_service = build_quote_service(db, force_live=True)

        seen_assets: set[tuple[str, str]] = set()
        status_counts = {
            "live": 0,
            "cache_fresh": 0,
            "cache_stale": 0,
            "avg_fallback": 0,
            "failed": 0,
        }

        for portfolio_id in portfolio_ids:
            for row in pos_repo.list_open_by_portfolio(portfolio_id):
                key = (str(row["asset_code"]).upper(), str(row["asset_type"]).lower())
                if key in seen_assets:
                    continue
                seen_assets.add(key)

                quote = quote_service.resolve_price(
                    row["asset_code"],
                    row["asset_type"],
                    force_refresh=True,
                )
                if quote is None:
                    status_counts["failed"] += 1
                    continue

                status = str(quote.get("status") or "failed")
                if status in status_counts:
                    status_counts[status] += 1
                else:
                    status_counts["failed"] += 1

        scope = "global" if len(portfolio_ids) != 1 else "portfolio"
        return QuoteRefreshResponse(
            scope=scope,
            portfolios=portfolio_ids,
            totalAssets=len(seen_assets),
            liveCount=status_counts["live"],
            cacheFreshCount=status_counts["cache_fresh"],
            cacheStaleCount=status_counts["cache_stale"],
            avgFallbackCount=status_counts["avg_fallback"],
            failedCount=status_counts["failed"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/portfolios", response_model=list[PortfolioOut])
    def list_portfolios(db: Database = Depends(get_db)) -> list[PortfolioOut]:  # noqa: B008
        repo = PortfolioRepository(db.connection)
        return [PortfolioOut(id=p.id, name=p.name, currency=p.base_currency) for p in repo.list_active()]

    @app.put("/api/portfolios/{portfolio_id}", response_model=PortfolioOut)
    def update_portfolio(
        portfolio_id: str,
        payload: PortfolioUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> PortfolioOut:
        repo = PortfolioRepository(db.connection)
        portfolio = repo.get(portfolio_id)
        if portfolio is None:
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name must not be empty")

        portfolio.name = name
        repo.upsert(portfolio)
        return PortfolioOut(id=portfolio.id, name=portfolio.name, currency=portfolio.base_currency)

    @app.get("/api/settings", response_model=AppSettingsOut)
    def get_settings(db: Database = Depends(get_db)) -> AppSettingsOut:  # noqa: B008
        def get_rate(key: str) -> float | None:
            row = db.connection.execute(
                f"SELECT value FROM app_settings WHERE key = '{key}'"
            ).fetchone()
            if row is None:
                return None
            try:
                return float(row["value"])
            except (TypeError, ValueError):
                return None

        return AppSettingsOut(
            cdiAnnualRate=get_rate("cdi_annual_rate"),
            selicAnnualRate=get_rate("selic_annual_rate"),
            ipcaAnnualRate=get_rate("ipca_annual_rate"),
        )

    @app.put("/api/settings", response_model=AppSettingsOut)
    def update_settings(
        payload: AppSettingsUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> AppSettingsOut:
        def validate_and_save(key: str, value: float | None) -> None:
            if value is None:
                db.connection.execute(
                    "DELETE FROM app_settings WHERE key = ?",
                    (key,),
                )
            else:
                # Values stored as percentage (e.g. 14.65 for 14.65% a.a.)
                if not math.isfinite(value) or value <= 0 or value >= 1000:
                    raise HTTPException(
                        status_code=422,
                        detail=f"{key} must be a percentage between 0 and 1000 (e.g. 14.65 for 14.65% a.a.)",
                    )
                db.connection.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value)),
                )

        validate_and_save("cdi_annual_rate", payload.cdiAnnualRate)
        validate_and_save("selic_annual_rate", payload.selicAnnualRate)
        validate_and_save("ipca_annual_rate", payload.ipcaAnnualRate)
        db.connection.commit()

        return AppSettingsOut(
            cdiAnnualRate=payload.cdiAnnualRate,
            selicAnnualRate=payload.selicAnnualRate,
            ipcaAnnualRate=payload.ipcaAnnualRate,
        )

    @app.post("/api/quotes/refresh", response_model=QuoteRefreshResponse)
    def refresh_all_quotes(db: Database = Depends(get_db)) -> QuoteRefreshResponse:  # noqa: B008
        repo = PortfolioRepository(db.connection)
        portfolio_ids = [portfolio.id for portfolio in repo.list_active()]
        return refresh_quotes_for_portfolios(db, portfolio_ids)

    @app.post("/api/portfolios/{portfolio_id}/quotes/refresh", response_model=QuoteRefreshResponse)
    def refresh_portfolio_quotes(
        portfolio_id: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> QuoteRefreshResponse:
        require_portfolio(portfolio_id, db)
        return refresh_quotes_for_portfolios(db, [portfolio_id])

    @app.get("/api/portfolios/{portfolio_id}/operations", response_model=OperationsResponse)
    def list_operations(
        portfolio_id: str,
        assetCode: str | None = Query(default=None),
        operationType: str | None = Query(default=None),
        startDate: str | None = Query(default=None),
        endDate: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=5000),
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
            quote = quote_service.resolve_price(
                row["asset_code"],
                row["asset_type"],
                fallback_price_cents=avg_price,
            )
            market_price = quote["price_cents"] if quote is not None else avg_price
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
                    quoteStatus=str(quote["status"]) if quote is not None else "avg_fallback",
                    quoteSource=str(quote["source"]) if quote is not None else "avg_price",
                    quoteAgeSeconds=(
                        int(quote["age_seconds"])
                        if quote is not None and quote.get("age_seconds") is not None
                        else None
                    ),
                )
            )

        fi_repo = FixedIncomePositionRepository(db.connection)
        prev_repo = PrevidenciaSnapshotRepository(db.connection)
        fi_positions = fi_repo.list_by_portfolio(
            portfolio_id,
            status="ACTIVE" if onlyOpen else None,
        )
        prev_positions = prev_repo.list_by_portfolio(portfolio_id)
        fi_valuation_service = _build_fixed_income_valuation_service(db)
        for position in fi_positions:
            valuation = fi_valuation_service.revalue(position)
            avg_price = int(position.principal_applied_brl)
            market_value = int(valuation.net_value_current_brl)
            unrealized = market_value - avg_price
            unrealized_pct = (unrealized / avg_price) if avg_price > 0 else 0.0
            code = position.external_id or f"RF-{position.id or position.application_date}"
            enriched.append(
                PositionOut(
                    assetCode=code,
                    name=_fixed_income_display_name(position),
                    assetClass="RENDA_FIXA",
                    quantity=1.0,
                    avgPrice=avg_price,
                    marketPrice=market_value,
                    marketValue=market_value,
                    unrealizedPnl=unrealized,
                    unrealizedPnlPct=unrealized_pct,
                    weight=0.0,
                    quoteStatus="avg_fallback",
                    quoteSource="fixed_income_valuation",
                    quoteAgeSeconds=None,
                )
            )

        for snapshot in prev_positions:
            market_value = int(snapshot.market_value_cents)
            enriched.append(
                PositionOut(
                    assetCode=snapshot.asset_code,
                    name=snapshot.product_name,
                    assetClass="PREVIDENCIA",
                    quantity=float(snapshot.quantity),
                    avgPrice=int(snapshot.unit_price_cents),
                    marketPrice=int(snapshot.unit_price_cents),
                    marketValue=market_value,
                    unrealizedPnl=0,
                    unrealizedPnlPct=0.0,
                    weight=0.0,
                    quoteStatus="avg_fallback",
                    quoteSource="previdencia_statement",
                    quoteAgeSeconds=None,
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
        fi_repo = FixedIncomePositionRepository(db.connection)
        prev_repo = PrevidenciaSnapshotRepository(db.connection)
        fi_positions = fi_repo.list_by_portfolio(portfolio_id, status="ACTIVE")
        prev_positions = prev_repo.list_by_portfolio(portfolio_id)
        fi_valuation_service = _build_fixed_income_valuation_service(db)
        quote_service = build_quote_service(db)

        total_invested = sum(int(row["total_cost"]) for row in positions)
        total_invested += sum(int(position.principal_applied_brl) for position in fi_positions)
        # Previdência snapshots have no historical cost — excluded from total_invested
        previdencia_total = sum(int(snapshot.market_value_cents) for snapshot in prev_positions)
        market_value_with_cost = 0
        for row in positions:
            avg_price = int(row["avg_price"])
            quote = quote_service.resolve_price(
                row["asset_code"],
                row["asset_type"],
                fallback_price_cents=avg_price,
            )
            price_cents = quote["price_cents"] if quote is not None else avg_price
            market_value_with_cost += int(round(float(row["quantity"]) * price_cents))
        for position in fi_positions:
            valuation = fi_valuation_service.revalue(position)
            market_value_with_cost += int(valuation.net_value_current_brl)
        # marketValue = full patrimônio including previdência; unrealized only on assets with known cost
        market_value = market_value_with_cost + previdencia_total
        unrealized = market_value_with_cost - total_invested
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
            avg_price = int(row["avg_price"])
            quote = quote_service.resolve_price(
                row["asset_code"],
                row["asset_type"],
                fallback_price_cents=avg_price,
            )
            price_cents = quote["price_cents"] if quote is not None else avg_price
            market_value_cents = int(round(float(row["quantity"]) * price_cents))
            allocation_by_class[klass] = allocation_by_class.get(klass, 0) + market_value_cents
        for position in fi_positions:
            valuation = fi_valuation_service.revalue(position)
            allocation_by_class["RENDA_FIXA"] = (
                allocation_by_class.get("RENDA_FIXA", 0)
                + int(valuation.net_value_current_brl)
            )
        for snapshot in prev_positions:
            allocation_by_class["PREVIDENCIA"] = (
                allocation_by_class.get("PREVIDENCIA", 0)
                + int(snapshot.market_value_cents)
            )

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
            previdenciaTotalValue=previdencia_total,
            allocation=allocation,
            performance=_build_performance_series(market_value),
        )

    # ------------------------------------------------------------------
    # Fixed-income (renda fixa) endpoints
    # ------------------------------------------------------------------

    def _serialize_fi(
        position: FixedIncomePosition,
        valuation_service: FixedIncomeValuationService,
    ) -> FixedIncomePositionOut:
        valuation = valuation_service.revalue(position)
        diff_gross = (
            position.imported_gross_value_brl - valuation.gross_value_current_brl
            if position.imported_gross_value_brl is not None
            else None
        )
        diff_net = (
            position.imported_net_value_brl - valuation.net_value_current_brl
            if position.imported_net_value_brl is not None
            else None
        )
        return FixedIncomePositionOut(
            id=position.id or 0,
            institution=position.institution,
            assetType=position.asset_type,
            productName=position.product_name,
            remunerationType=position.remuneration_type,
            benchmark=position.benchmark,
            investorType=position.investor_type,
            currency=position.currency,
            applicationDate=position.application_date,
            maturityDate=position.maturity_date,
            liquidityLabel=position.liquidity_label,
            principalAppliedBrl=position.principal_applied_brl,
            fixedRateAnnualPercent=position.fixed_rate_annual_percent,
            benchmarkPercent=position.benchmark_percent,
            grossValueCurrentBrl=valuation.gross_value_current_brl,
            grossIncomeCurrentBrl=valuation.gross_income_current_brl,
            estimatedIrCurrentBrl=valuation.estimated_ir_current_brl,
            netValueCurrentBrl=valuation.net_value_current_brl,
            taxBracketCurrent=valuation.tax_bracket_current,
            daysSinceApplication=valuation.days_since_application,
            valuationDate=valuation.valuation_date,
            isComplete=valuation.is_complete,
            incompleteReason=valuation.incomplete_reason,
            status=position.status,
            importedGrossValueBrl=position.imported_gross_value_brl,
            importedNetValueBrl=position.imported_net_value_brl,
            importedEstimatedIrBrl=position.imported_estimated_ir_brl,
            grossDiffBrl=diff_gross,
            netDiffBrl=diff_net,
            notes=position.notes,
        )

    @app.get(
        "/api/portfolios/{portfolio_id}/fixed-income",
        response_model=FixedIncomePositionsResponse,
    )
    def list_fixed_income(
        portfolio_id: str,
        status: str | None = Query(default=None),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionsResponse:
        require_portfolio(portfolio_id, db)
        repo = FixedIncomePositionRepository(db.connection)
        positions = repo.list_by_portfolio(portfolio_id, status=status)
        valuation_service = _build_fixed_income_valuation_service(db)
        items = [_serialize_fi(p, valuation_service) for p in positions]
        return FixedIncomePositionsResponse(positions=items)

    @app.get(
        "/api/portfolios/{portfolio_id}/fixed-income/{position_id}",
        response_model=FixedIncomePositionOut,
    )
    def get_fixed_income(
        portfolio_id: str,
        position_id: int,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionOut:
        require_portfolio(portfolio_id, db)
        repo = FixedIncomePositionRepository(db.connection)
        position = repo.get(position_id)
        if position is None or position.portfolio_id != portfolio_id:
            raise HTTPException(status_code=404, detail="Position not found")
        return _serialize_fi(position, _build_fixed_income_valuation_service(db))

    @app.post(
        "/api/portfolios/{portfolio_id}/fixed-income",
        response_model=FixedIncomePositionOut,
        status_code=201,
    )
    def create_fixed_income(
        portfolio_id: str,
        payload: FixedIncomePositionCreate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionOut:
        require_portfolio(portfolio_id, db)
        try:
            position = FixedIncomePosition(
                portfolio_id=portfolio_id,
                institution=payload.institution,
                asset_type=payload.assetType,
                product_name=payload.productName,
                remuneration_type=payload.remunerationType,
                benchmark=payload.benchmark or (
                    "CDI" if payload.remunerationType == "CDI_PERCENT" else "NONE"
                ),
                investor_type="PF",
                currency="BRL",
                application_date=payload.applicationDate,
                maturity_date=payload.maturityDate,
                principal_applied_brl=payload.principalAppliedBrl,
                liquidity_label=payload.liquidityLabel,
                fixed_rate_annual_percent=payload.fixedRateAnnualPercent,
                benchmark_percent=payload.benchmarkPercent,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        repo = FixedIncomePositionRepository(db.connection)
        repo.insert(position)
        return _serialize_fi(position, _build_fixed_income_valuation_service(db))

    @app.post(
        "/api/portfolios/{portfolio_id}/fixed-income/import-csv",
        response_model=FixedIncomeImportResponse,
    )
    async def import_fixed_income_csv(
        portfolio_id: str,
        file: UploadFile,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomeImportResponse:
        require_portfolio(portfolio_id, db)
        raw = await file.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        result = FixedIncomeCSVImporter().parse_text(text, portfolio_id=portfolio_id)
        repo = FixedIncomePositionRepository(db.connection)
        for position in result.valid:
            repo.insert(position)

        valuation_service = _build_fixed_income_valuation_service(db)
        items = [_serialize_fi(p, valuation_service) for p in result.valid]
        errors = [
            FixedIncomeImportError(
                rowIndex=err.row_index,
                message=err.message,
                field=err.field,
            )
            for err in result.errors
        ]
        return FixedIncomeImportResponse(
            imported=len(items),
            failed=len(errors),
            positions=items,
            errors=errors,
        )

    return app


app = create_http_app()
