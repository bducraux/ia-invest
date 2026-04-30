"""HTTP API for IA-Invest frontend integration.

This module exposes a FastAPI app that adapts existing repository/domain data
to the frontend contracts. It intentionally reuses the current storage and MCP
tool logic to keep business rules centralized.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import SQLiteDailyRateProvider
from domain.fixed_income_valuation import FixedIncomeValuationService
from domain.members import MemberService, MemberServiceError
from domain.portfolio_service import PortfolioService
from domain.position_service import PositionService
from mcp_server.services.benchmark_sync import (
    BACENBenchmarkSyncService,
    BenchmarkSyncError,
    SyncResult,
)
from mcp_server.services.fixed_income_lifecycle import FixedIncomeLifecycleService
from mcp_server.services.fx_rates import SUPPORTED_PAIRS as FX_SUPPORTED_PAIRS
from mcp_server.services.fx_rates import FxRateService
from mcp_server.services.fx_sync import FxSyncError, FxSyncResult, FxSyncService
from mcp_server.services.position_lifecycle import PositionLifecycleService
from mcp_server.services.quotes import MarketQuoteService
from mcp_server.tools.app_settings import get_app_settings
from mcp_server.tools.concentration import get_concentration_analysis
from mcp_server.tools.dividends_summary import get_dividends_summary
from mcp_server.tools.fixed_income_summary import get_fixed_income_summary
from mcp_server.tools.performance import get_portfolio_performance
from mcp_server.tools.portfolio_alerts import get_portfolio_alerts
from mcp_server.tools.portfolios import get_portfolio_operations
from mcp_server.tools.positions_with_quote import get_position_with_quote
from normalizers.fixed_income_csv import FixedIncomeCSVImporter
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.fx_rates import FxRatesRepository
from storage.repository.members import MemberRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository

_DEFAULT_DB_PATH = Path(os.environ.get("IA_INVEST_DB", "ia_invest.db"))
_DEFAULT_CORS_ORIGINS = os.environ.get("IA_INVEST_API_CORS_ORIGINS", "http://localhost:3000")
_DEFAULT_QUOTES_ENABLED = os.environ.get("IA_INVEST_QUOTES_ENABLED", "1")
_DEFAULT_QUOTES_TTL_SECONDS = int(os.environ.get("IA_INVEST_QUOTES_TTL_SECONDS", "300"))
_DEFAULT_QUOTES_TIMEOUT_SECONDS = float(os.environ.get("IA_INVEST_QUOTES_TIMEOUT_SECONDS", "2.0"))
_DEFAULT_BENCHMARK_AUTO_SYNC = os.environ.get("IA_INVEST_BENCHMARK_AUTO_SYNC", "1")

# Per-process throttle for the best-effort CDI auto-sync triggered by HTTP
# requests. Without it the server would hit BACEN on every single request.
_CDI_AUTO_SYNC_MIN_INTERVAL = timedelta(hours=1)
_CDI_AUTO_SYNC_STATE: dict[str, datetime] = {}


class OwnerSummary(BaseModel):
    id: str
    name: str
    displayName: str | None = None
    email: str | None = None
    status: str = "active"


class PortfolioOut(BaseModel):
    id: str
    name: str
    currency: str = "BRL"
    allowedAssetTypes: list[str] = []
    specialization: str = "GENERIC"
    ownerId: str
    owner: OwnerSummary | None = None


class PortfolioUpdate(BaseModel):
    name: str
    ownerId: str | None = None


class TransferOwnerRequest(BaseModel):
    newOwnerId: str


class MemberCreate(BaseModel):
    id: str
    name: str
    displayName: str | None = None
    email: str | None = None


class MemberUpdate(BaseModel):
    name: str | None = None
    displayName: str | None = None
    email: str | None = None
    status: str | None = None  # active | inactive


class MemberOut(BaseModel):
    id: str
    name: str
    displayName: str | None = None
    email: str | None = None
    status: str = "active"
    portfolioCount: int = 0
    createdAt: str | None = None
    updatedAt: str | None = None


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
    assetType: str
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


class BenchmarkCoverageOut(BaseModel):
    benchmark: str
    coverageStart: str | None = None
    coverageEnd: str | None = None
    rowCount: int = 0
    lastFetchedAt: str | None = None


class BenchmarkSyncRequest(BaseModel):
    startDate: str | None = None
    endDate: str | None = None
    fullRefresh: bool = False


class BenchmarkSyncResultOut(BaseModel):
    benchmark: str
    rowsInserted: int
    coverageStart: str | None = None
    coverageEnd: str | None = None
    source: str
    lastFetchedAt: str | None = None


class FxCoverageOut(BaseModel):
    pair: str
    coverageStart: str | None = None
    coverageEnd: str | None = None
    rowCount: int = 0
    lastFetchedAt: str | None = None


class FxSyncRequest(BaseModel):
    startDate: str | None = None
    endDate: str | None = None
    fullRefresh: bool = False


class FxSyncResultOut(BaseModel):
    pair: str
    rowsInserted: int
    coverageStart: str | None = None
    coverageEnd: str | None = None
    source: str
    lastFetchedAt: str | None = None


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
    autoReapplyEnabled: bool = False


class FixedIncomePositionUpdate(BaseModel):
    institution: str | None = None
    assetType: str | None = None
    productName: str | None = None
    remunerationType: str | None = None
    benchmark: str | None = None
    applicationDate: str | None = None
    maturityDate: str | None = None
    principalAppliedBrl: int | None = None
    fixedRateAnnualPercent: float | None = None
    benchmarkPercent: float | None = None
    liquidityLabel: str | None = None
    notes: str | None = None


class FixedIncomeLifecycleActionIn(BaseModel):
    asOfDate: str | None = None


class FixedIncomeAutoReapplyUpdate(BaseModel):
    enabled: bool


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
    autoReapplyEnabled: bool
    isMatured: bool
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


# --- Operations CRUD ---------------------------------------------------------


class OperationUpdate(BaseModel):
    """Whitelisted patch payload for editing a single operation.

    All fields are optional. ``externalId`` is intentionally absent: it is
    automatically neutralised on every edit to avoid future UNIQUE-constraint
    conflicts when reimporting the original source file.
    """

    assetCode: str | None = None
    assetName: str | None = None
    assetType: str | None = None
    operationType: str | None = None
    operationDate: str | None = None
    settlementDate: str | None = None
    quantity: float | None = None
    unitPrice: int | None = None
    grossValue: int | None = None
    fees: int | None = None
    netValue: int | None = None
    notes: str | None = None
    broker: str | None = None
    account: str | None = None


_OPERATION_FIELD_MAP: dict[str, str] = {
    "assetCode": "asset_code",
    "assetName": "asset_name",
    "assetType": "asset_type",
    "operationType": "operation_type",
    "operationDate": "operation_date",
    "settlementDate": "settlement_date",
    "quantity": "quantity",
    "unitPrice": "unit_price",
    "grossValue": "gross_value",
    "fees": "fees",
    "netValue": "net_value",
    "notes": "notes",
    "broker": "broker",
    "account": "account",
}


class OperationCreate(BaseModel):
    """Payload for creating a manual operation entry.

    Required: assetCode, assetType, operationType, operationDate, quantity,
    unitPrice (cents), grossValue (cents). Optional: assetName, fees,
    netValue, settlementDate, broker, account, notes.
    """

    assetCode: str
    assetType: str
    operationType: str
    operationDate: str
    quantity: float
    unitPrice: int
    grossValue: int
    assetName: str | None = None
    settlementDate: str | None = None
    fees: int | None = None
    netValue: int | None = None
    notes: str | None = None
    broker: str | None = None
    account: str | None = None


_OPERATION_CREATE_FIELD_MAP: dict[str, str] = {
    **_OPERATION_FIELD_MAP,
}


# --- Previdencia CRUD --------------------------------------------------------


class PrevidenciaSnapshotUpdate(BaseModel):
    productName: str | None = None
    quantity: float | None = None
    unitPriceCents: int | None = None
    marketValueCents: int | None = None
    periodMonth: str | None = None
    periodStartDate: str | None = None
    periodEndDate: str | None = None


_PREVIDENCIA_FIELD_MAP: dict[str, str] = {
    "productName": "product_name",
    "quantity": "quantity",
    "unitPriceCents": "unit_price_cents",
    "marketValueCents": "market_value_cents",
    "periodMonth": "period_month",
    "periodStartDate": "period_start_date",
    "periodEndDate": "period_end_date",
}


def _to_snake_payload(
    payload: BaseModel, field_map: dict[str, str]
) -> dict[str, Any]:
    raw = payload.model_dump(exclude_unset=True)
    return {field_map[k]: v for k, v in raw.items() if k in field_map}


def _to_ui_operation_type(operation_type: str) -> str:
    mapping = {
        "buy": "COMPRA",
        "sell": "VENDA",
        "dividend": "DIVIDENDO",
        "jcp": "JCP",
        "rendimento": "RENDIMENTO",
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
        "stock_us": "INTERNACIONAL",
        "etf_us": "INTERNACIONAL",
        "reit_us": "INTERNACIONAL",
        "bdr_us": "INTERNACIONAL",
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
        "INTERNACIONAL": "Internacional",
    }
    return labels.get(asset_class, asset_class)


def _portfolio_specialization(allowed_asset_types: list[str]) -> str:
    normalized = {asset_type.strip().lower() for asset_type in allowed_asset_types}
    if not normalized:
        return "GENERIC"
    if normalized <= {"cdb", "lci", "lca", "bond", "treasury"}:
        return "RENDA_FIXA"
    if normalized <= {"previdencia"}:
        return "PREVIDENCIA"
    if normalized <= {"stock", "fii", "etf", "bdr"}:
        return "RENDA_VARIAVEL"
    if normalized <= {"crypto"}:
        return "CRIPTO"
    if normalized <= {"stock_us", "etf_us", "reit_us", "bdr_us"}:
        return "INTERNACIONAL"
    return "GENERIC"


def _matches_ui_asset_class(asset_class: str | None, ui_asset_class: str) -> bool:
    if asset_class is None:
        return True
    if asset_class == "RENDA_VARIAVEL":
        return ui_asset_class in {"ACAO", "FII", "ETF"}
    return ui_asset_class == asset_class


def _matches_asset_class(asset_class: str | None, asset_type: str) -> bool:
    return _matches_ui_asset_class(asset_class, _to_ui_asset_class(asset_type))


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
    """Build valuation service with BACEN-backed historical CDI only.

    Resolution order:

    1. ``daily_benchmark_rates`` table (BACEN SGS cache) — authoritative.
       When auto-sync is enabled, perform best-effort incremental refresh.
    2. If cache is empty, perform one best-effort sync immediately.
    3. If still empty, return valuation service without CDI provider
       (CDI positions become ``isComplete = false`` until sync succeeds).
    """
    repo = BenchmarkRatesRepository(db.connection)

    auto_sync = _parse_bool_flag(_DEFAULT_BENCHMARK_AUTO_SYNC)
    if auto_sync:
        _maybe_auto_sync_cdi(repo)

    _, coverage_end, row_count = repo.get_coverage("CDI")
    if row_count == 0 or coverage_end is None:
        try:
            BACENBenchmarkSyncService(repo).sync("CDI")
            _, coverage_end, row_count = repo.get_coverage("CDI")
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "cdi_initial_sync_failed: %s — CDI valuations may be incomplete until sync succeeds",
                exc,
            )

    if row_count > 0 and coverage_end is not None:
        return FixedIncomeValuationService(cdi_provider=SQLiteDailyRateProvider(repo))

    return FixedIncomeValuationService()


def _maybe_auto_sync_cdi(repo: BenchmarkRatesRepository) -> None:
    """Best-effort incremental BACEN sync. Never raises.

    Throttled per-process: at most one sync attempt per hour, and skipped
    entirely when the cache already covers today. This avoids hammering
    BACEN on every HTTP request.
    """
    try:
        _, coverage_end, _ = repo.get_coverage("CDI")
        today = date.today()
        if coverage_end is not None and coverage_end >= today:
            return

        now = datetime.now()
        last_attempt = _CDI_AUTO_SYNC_STATE.get("last_attempt")
        if last_attempt is not None and (now - last_attempt) < _CDI_AUTO_SYNC_MIN_INTERVAL:
            return
        _CDI_AUTO_SYNC_STATE["last_attempt"] = now

        sync = BACENBenchmarkSyncService(repo)
        sync.sync("CDI")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "cdi_auto_sync_failed: %s — keeping existing CDI cache",
            exc,
        )


def _build_fixed_income_lifecycle_service(db: Database) -> FixedIncomeLifecycleService:
    repo = FixedIncomePositionRepository(db.connection)
    valuation = _build_fixed_income_valuation_service(db)
    return FixedIncomeLifecycleService(repo=repo, valuation_service=valuation)


def _build_position_lifecycle_service(db: Database) -> PositionLifecycleService:
    op_repo = OperationRepository(db.connection)
    pos_repo = PositionRepository(db.connection)
    return PositionLifecycleService(
        conn=db.connection,
        operation_repo=op_repo,
        position_repo=pos_repo,
        position_service=PositionService(),
    )


def _is_matured(maturity_date: str, valuation_date: str) -> bool:
    return maturity_date <= valuation_date


def _merge_fixed_income_position(
    current: FixedIncomePosition,
    payload: FixedIncomePositionUpdate,
) -> FixedIncomePosition:
    remuneration_type = payload.remunerationType or current.remuneration_type
    merged_benchmark = payload.benchmark
    if merged_benchmark is None:
        merged_benchmark = "CDI" if remuneration_type == "CDI_PERCENT" else "NONE"

    return FixedIncomePosition(
        id=current.id,
        portfolio_id=current.portfolio_id,
        import_job_id=current.import_job_id,
        external_id=current.external_id,
        institution=payload.institution or current.institution,
        asset_type=payload.assetType or current.asset_type,
        product_name=payload.productName or current.product_name,
        remuneration_type=remuneration_type,
        benchmark=merged_benchmark,
        investor_type=current.investor_type,
        currency=current.currency,
        application_date=payload.applicationDate or current.application_date,
        maturity_date=payload.maturityDate or current.maturity_date,
        principal_applied_brl=(
            payload.principalAppliedBrl
            if payload.principalAppliedBrl is not None
            else current.principal_applied_brl
        ),
        liquidity_label=(
            payload.liquidityLabel
            if payload.liquidityLabel is not None
            else current.liquidity_label
        ),
        fixed_rate_annual_percent=(
            payload.fixedRateAnnualPercent
            if payload.fixedRateAnnualPercent is not None
            else current.fixed_rate_annual_percent
        ),
        benchmark_percent=(
            payload.benchmarkPercent
            if payload.benchmarkPercent is not None
            else current.benchmark_percent
        ),
        notes=payload.notes if payload.notes is not None else current.notes,
        status=current.status,
        auto_reapply_enabled=current.auto_reapply_enabled,
    )


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
        fx_repo = FxRatesRepository(db.connection)
        fx_service = FxRateService(fx_repo, live_ttl_seconds=_DEFAULT_QUOTES_TTL_SECONDS)
        return MarketQuoteService(
            db.connection,
            enabled=(resolved_quotes_enabled or force_live),
            ttl_seconds=_DEFAULT_QUOTES_TTL_SECONDS,
            timeout_seconds=_DEFAULT_QUOTES_TIMEOUT_SECONDS,
            fx_service=fx_service,
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

    def _owner_summary(db: Database, owner_id: str) -> OwnerSummary | None:
        member = MemberRepository(db.connection).get(owner_id)
        if member is None:
            return OwnerSummary(id=owner_id, name=owner_id, status="unknown")
        return OwnerSummary(
            id=member.id,
            name=member.name,
            displayName=member.display_name,
            email=member.email,
            status=member.status,
        )

    def _portfolio_to_out(db: Database, portfolio: Any) -> PortfolioOut:
        return PortfolioOut(
            id=portfolio.id,
            name=portfolio.name,
            currency=portfolio.base_currency,
            allowedAssetTypes=portfolio.allowed_asset_types,
            specialization=_portfolio_specialization(portfolio.allowed_asset_types),
            ownerId=portfolio.owner_id,
            owner=_owner_summary(db, portfolio.owner_id),
        )

    def _member_to_out(db: Database, member: Any) -> MemberOut:
        repo = MemberRepository(db.connection)
        return MemberOut(
            id=member.id,
            name=member.name,
            displayName=member.display_name,
            email=member.email,
            status=member.status,
            portfolioCount=repo.count_portfolios(member.id, only_active=True),
            createdAt=member.created_at,
            updatedAt=member.updated_at,
        )

    @app.get("/api/portfolios", response_model=list[PortfolioOut])
    def list_portfolios(
        owner_id: str | None = Query(default=None, alias="ownerId"),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> list[PortfolioOut]:
        repo = PortfolioRepository(db.connection)
        portfolios = (
            repo.list_by_owner(owner_id, only_active=True)
            if owner_id
            else repo.list_active()
        )
        return [_portfolio_to_out(db, p) for p in portfolios]

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

        if payload.ownerId:
            new_owner = payload.ownerId.strip().lower()
            if MemberRepository(db.connection).get(new_owner) is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Member '{new_owner}' not found",
                )
            portfolio.owner_id = new_owner

        repo.upsert(portfolio)
        return _portfolio_to_out(db, portfolio)

    @app.post(
        "/api/portfolios/{portfolio_id}/transfer-owner",
        response_model=PortfolioOut,
    )
    def transfer_portfolio_owner(
        portfolio_id: str,
        payload: TransferOwnerRequest,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> PortfolioOut:
        portfolio_repo = PortfolioRepository(db.connection)
        member_repo = MemberRepository(db.connection)
        svc = PortfolioService(
            portfolio_repo=portfolio_repo, member_repo=member_repo
        )
        try:
            portfolio = svc.transfer_ownership(portfolio_id, payload.newOwnerId)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _portfolio_to_out(db, portfolio)

    # ------------------------------------------------------------------ Members
    @app.get("/api/members", response_model=list[MemberOut])
    def list_members(
        status: str | None = Query(default=None),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> list[MemberOut]:
        repo = MemberRepository(db.connection)
        if status == "active":
            members = repo.list_active()
        elif status == "inactive":
            members = [m for m in repo.list_all() if m.status == "inactive"]
        else:
            members = repo.list_all()
        return [_member_to_out(db, m) for m in members]

    @app.get("/api/members/{member_id}", response_model=MemberOut)
    def get_member(
        member_id: str, db: Database = Depends(get_db)  # noqa: B008
    ) -> MemberOut:
        repo = MemberRepository(db.connection)
        member = repo.get(member_id) or repo.get_by_id_or_name(member_id)
        if member is None:
            raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found")
        return _member_to_out(db, member)

    @app.post("/api/members", response_model=MemberOut, status_code=201)
    def create_member(
        payload: MemberCreate, db: Database = Depends(get_db)  # noqa: B008
    ) -> MemberOut:
        svc = MemberService(
            MemberRepository(db.connection), PortfolioRepository(db.connection)
        )
        try:
            member = svc.create(
                member_id=payload.id,
                name=payload.name,
                display_name=payload.displayName,
                email=payload.email,
            )
        except MemberServiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _member_to_out(db, member)

    @app.patch("/api/members/{member_id}", response_model=MemberOut)
    def update_member(
        member_id: str,
        payload: MemberUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> MemberOut:
        svc = MemberService(
            MemberRepository(db.connection), PortfolioRepository(db.connection)
        )
        try:
            updated = svc.update(
                member_id,
                name=payload.name,
                display_name=payload.displayName,
                email=payload.email,
            )
            if payload.status == "active":
                updated = svc.activate(member_id)
            elif payload.status == "inactive":
                updated = svc.inactivate(member_id)
        except MemberServiceError as exc:
            status_code = 404 if "not found" in str(exc) else 422
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return _member_to_out(db, updated)

    @app.delete("/api/members/{member_id}", status_code=204)
    def delete_member(
        member_id: str, db: Database = Depends(get_db)  # noqa: B008
    ) -> None:
        svc = MemberService(
            MemberRepository(db.connection), PortfolioRepository(db.connection)
        )
        try:
            svc.delete(member_id)
        except MemberServiceError as exc:
            status_code = 404 if "not found" in str(exc) else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get(
        "/api/members/{member_id}/portfolios",
        response_model=list[PortfolioOut],
    )
    def get_member_portfolios(
        member_id: str, db: Database = Depends(get_db)  # noqa: B008
    ) -> list[PortfolioOut]:
        member_repo = MemberRepository(db.connection)
        member = member_repo.get(member_id) or member_repo.get_by_id_or_name(member_id)
        if member is None:
            raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found")
        portfolios = PortfolioRepository(db.connection).list_by_owner(
            member.id, only_active=True
        )
        return [_portfolio_to_out(db, p) for p in portfolios]

    @app.get("/api/members/{member_id}/summary")
    def get_member_summary_endpoint(
        member_id: str, db: Database = Depends(get_db)  # noqa: B008
    ) -> dict[str, Any]:
        from mcp_server.tools.members import get_member_summary

        result = get_member_summary(db, member_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.get("/api/members/{member_id}/positions")
    def get_member_positions_endpoint(
        member_id: str,
        open_only: bool = Query(default=True, alias="openOnly"),
        db: Database = Depends(get_db),  # noqa: B008
    ) -> list[dict[str, Any]]:
        from mcp_server.tools.members import get_member_positions

        result = get_member_positions(db, member_id, open_only=open_only)
        if result and "error" in result[0]:
            raise HTTPException(status_code=404, detail=result[0]["error"])
        return result

    @app.get("/api/benchmarks/{benchmark}/coverage", response_model=BenchmarkCoverageOut)
    def get_benchmark_coverage(
        benchmark: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> BenchmarkCoverageOut:
        bench = benchmark.upper()
        repo = BenchmarkRatesRepository(db.connection)
        start, end, count = repo.get_coverage(bench)
        return BenchmarkCoverageOut(
            benchmark=bench,
            coverageStart=start.isoformat() if start else None,
            coverageEnd=end.isoformat() if end else None,
            rowCount=count,
            lastFetchedAt=repo.get_last_fetched_at(bench),
        )

    @app.post("/api/benchmarks/{benchmark}/sync", response_model=BenchmarkSyncResultOut)
    def sync_benchmark(
        benchmark: str,
        payload: BenchmarkSyncRequest | None = None,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> BenchmarkSyncResultOut:
        bench = benchmark.upper()
        repo = BenchmarkRatesRepository(db.connection)
        service = BACENBenchmarkSyncService(repo)
        body = payload or BenchmarkSyncRequest()

        def _parse_iso_date(label: str, raw: str | None) -> date | None:
            if raw is None:
                return None
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{label} must be ISO date YYYY-MM-DD",
                ) from exc

        try:
            result: SyncResult = service.sync(
                bench,
                start_date=_parse_iso_date("startDate", body.startDate),
                end_date=_parse_iso_date("endDate", body.endDate),
                full_refresh=body.fullRefresh,
            )
        except BenchmarkSyncError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return BenchmarkSyncResultOut(
            benchmark=result.benchmark,
            rowsInserted=result.rows_inserted,
            coverageStart=result.coverage_start.isoformat() if result.coverage_start else None,
            coverageEnd=result.coverage_end.isoformat() if result.coverage_end else None,
            source=result.source,
            lastFetchedAt=repo.get_last_fetched_at(bench),
        )

    @app.get("/api/fx/{pair}/coverage", response_model=FxCoverageOut)
    def get_fx_coverage(
        pair: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FxCoverageOut:
        pair_u = pair.upper()
        if pair_u not in FX_SUPPORTED_PAIRS:
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported FX pair '{pair}'. Supported: {', '.join(FX_SUPPORTED_PAIRS)}",
            )
        repo = FxRatesRepository(db.connection)
        start, end, count = repo.get_coverage(pair_u)
        return FxCoverageOut(
            pair=pair_u,
            coverageStart=start.isoformat() if start else None,
            coverageEnd=end.isoformat() if end else None,
            rowCount=count,
            lastFetchedAt=repo.get_last_fetched_at(pair_u),
        )

    @app.post("/api/fx/{pair}/sync", response_model=FxSyncResultOut)
    def sync_fx(
        pair: str,
        payload: FxSyncRequest | None = None,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FxSyncResultOut:
        pair_u = pair.upper()
        if pair_u not in FX_SUPPORTED_PAIRS:
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported FX pair '{pair}'. Supported: {', '.join(FX_SUPPORTED_PAIRS)}",
            )
        repo = FxRatesRepository(db.connection)
        service = FxSyncService(repo)
        body = payload or FxSyncRequest()

        def _parse_iso_date(label: str, raw: str | None) -> date | None:
            if raw is None:
                return None
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{label} must be ISO date YYYY-MM-DD",
                ) from exc

        try:
            result: FxSyncResult = service.sync(
                pair_u,
                start_date=_parse_iso_date("startDate", body.startDate),
                end_date=_parse_iso_date("endDate", body.endDate),
                full_refresh=body.fullRefresh,
            )
        except FxSyncError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return FxSyncResultOut(
            pair=result.pair,
            rowsInserted=result.rows_inserted,
            coverageStart=result.coverage_start.isoformat() if result.coverage_start else None,
            coverageEnd=result.coverage_end.isoformat() if result.coverage_end else None,
            source=result.source,
            lastFetchedAt=repo.get_last_fetched_at(result.pair),
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
        assetClass: str | None = Query(default=None),
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

        op_repo = OperationRepository(db.connection)
        if assetClass is None:
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
            total = _count_operations(
                op_repo,
                portfolio_id,
                asset_code=assetCode,
                operation_type=op_type,
                start_date=startDate,
                end_date=endDate,
            )
        else:
            filtered_rows = [
                row
                for row in op_repo.list_all_by_portfolio(
                    portfolio_id,
                    asset_code=assetCode,
                    operation_type=op_type,
                    start_date=startDate,
                    end_date=endDate,
                )
                if _matches_asset_class(assetClass, str(row["asset_type"]))
            ]
            total = len(filtered_rows)
            rows = filtered_rows[offset: offset + limit]

        mapped = [
            OperationOut(
                id=str(row["id"]),
                date=row["operation_date"],
                assetCode=row["asset_code"],
                assetType=str(row["asset_type"] or ""),
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
        assetClass: str | None = Query(default=None),
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

        if assetClass is not None:
            enriched = [
                position
                for position in enriched
                if _matches_ui_asset_class(assetClass, position.assetClass)
            ]

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
        is_matured = _is_matured(position.maturity_date, valuation.valuation_date)
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
            autoReapplyEnabled=position.auto_reapply_enabled,
            isMatured=is_matured,
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
        _build_fixed_income_lifecycle_service(db).reconcile_auto_reapply(portfolio_id)
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
        _build_fixed_income_lifecycle_service(db).reconcile_auto_reapply(portfolio_id)
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
                auto_reapply_enabled=payload.autoReapplyEnabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        repo = FixedIncomePositionRepository(db.connection)
        repo.insert(position)
        return _serialize_fi(position, _build_fixed_income_valuation_service(db))

    @app.patch(
        "/api/portfolios/{portfolio_id}/fixed-income/{position_id}",
        response_model=FixedIncomePositionOut,
    )
    def update_fixed_income(
        portfolio_id: str,
        position_id: int,
        payload: FixedIncomePositionUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionOut:
        require_portfolio(portfolio_id, db)
        repo = FixedIncomePositionRepository(db.connection)
        current = repo.get(position_id)
        if current is None or current.portfolio_id != portfolio_id:
            raise HTTPException(status_code=404, detail="Position not found")

        try:
            updated = _merge_fixed_income_position(current, payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        repo.update(updated)
        persisted = repo.get(position_id)
        if persisted is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return _serialize_fi(persisted, _build_fixed_income_valuation_service(db))

    @app.delete(
        "/api/portfolios/{portfolio_id}/fixed-income/{position_id}",
        status_code=204,
    )
    def close_fixed_income(
        portfolio_id: str,
        position_id: int,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> None:
        """Close (delete) a fixed-income position without reinvesting."""
        require_portfolio(portfolio_id, db)
        lifecycle = _build_fixed_income_lifecycle_service(db)
        try:
            lifecycle.close(portfolio_id, position_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/portfolios/{portfolio_id}/fixed-income/{position_id}/redeem",
        response_model=FixedIncomePositionOut,
    )
    def redeem_fixed_income(
        portfolio_id: str,
        position_id: int,
        payload: FixedIncomeLifecycleActionIn,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionOut:
        """Reinvest proceeds: create new position with net value, delete old."""
        require_portfolio(portfolio_id, db)
        lifecycle = _build_fixed_income_lifecycle_service(db)
        try:
            position = lifecycle.redeem(
                portfolio_id,
                position_id,
                as_of_date=payload.asOfDate,
            )
        except ValueError as exc:
            detail = str(exc)
            if detail == "Position not found":
                raise HTTPException(status_code=404, detail=detail) from exc
            raise HTTPException(status_code=422, detail=detail) from exc

        return _serialize_fi(position, _build_fixed_income_valuation_service(db))

    @app.patch(
        "/api/portfolios/{portfolio_id}/fixed-income/{position_id}/auto-reapply",
        response_model=FixedIncomePositionOut,
    )
    def toggle_auto_reapply_fixed_income(
        portfolio_id: str,
        position_id: int,
        payload: FixedIncomeAutoReapplyUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> FixedIncomePositionOut:
        require_portfolio(portfolio_id, db)
        repo = FixedIncomePositionRepository(db.connection)
        position = repo.get(position_id)
        if position is None or position.portfolio_id != portfolio_id:
            raise HTTPException(status_code=404, detail="Position not found")

        repo.set_auto_reapply(position_id, portfolio_id, payload.enabled)
        updated = repo.get(position_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return _serialize_fi(updated, _build_fixed_income_valuation_service(db))

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

    # ------------------------------------------------------------------
    # MCP analytical tools exposed as read-only REST endpoints.
    #
    # These are thin proxies over ``mcp_server.tools.*`` so the Next.js
    # frontend can consume the same payloads the MCP server returns.
    # Responses are emitted verbatim (snake_case) — the tool dicts are the
    # contract; the frontend adapts when needed. No Pydantic remapping is
    # applied to keep these mirrors of the MCP protocol.
    # ------------------------------------------------------------------

    @app.get("/api/settings", response_model=None)
    def settings_endpoint() -> dict[str, Any]:
        db = get_db()
        return get_app_settings(db)

    @app.get("/api/portfolios/{portfolio_id}/positions-with-quote", response_model=None)
    def positions_with_quote_endpoint(
        portfolio_id: str,
        asset_code: str | None = Query(default=None),
    ) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        result = get_position_with_quote(
            db,
            portfolio_id,
            asset_code=asset_code,
            quote_service=build_quote_service(db),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/api/portfolios/{portfolio_id}/dividends-summary", response_model=None)
    def dividends_summary_endpoint(
        portfolio_id: str,
        period_months: int = Query(default=12, ge=1, le=120),
    ) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        result = get_dividends_summary(
            db,
            portfolio_id,
            period_months=period_months,
            quote_service=build_quote_service(db),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/api/portfolios/{portfolio_id}/concentration", response_model=None)
    def concentration_endpoint(portfolio_id: str) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        result = get_concentration_analysis(
            db,
            portfolio_id,
            quote_service=build_quote_service(db),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/api/portfolios/{portfolio_id}/performance", response_model=None)
    def performance_endpoint(
        portfolio_id: str,
        period_months: int = Query(default=12, ge=1, le=120),
    ) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        result = get_portfolio_performance(
            db,
            portfolio_id,
            period_months=period_months,
            quote_service=build_quote_service(db),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/api/portfolios/{portfolio_id}/fixed-income-summary", response_model=None)
    def fixed_income_summary_endpoint(
        portfolio_id: str,
        as_of: str | None = Query(default=None),
    ) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        as_of_date: date | None = None
        if as_of:
            try:
                as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid as_of (expected YYYY-MM-DD): {as_of}",
                ) from exc
        result = get_fixed_income_summary(db, portfolio_id, as_of=as_of_date)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/api/portfolios/{portfolio_id}/alerts", response_model=None)
    def alerts_endpoint(portfolio_id: str) -> dict[str, Any]:
        db = get_db()
        require_portfolio(portfolio_id, db)
        result = get_portfolio_alerts(
            db,
            portfolio_id,
            quote_service=build_quote_service(db),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ------------------------------------------------------------------
    # Position lifecycle (close) and operation CRUD — event-sourced
    # portfolios (renda variavel, cripto, internacional). Renda fixa has
    # its own dedicated endpoints above.
    # ------------------------------------------------------------------

    @app.delete(
        "/api/portfolios/{portfolio_id}/positions/{asset_code}",
        status_code=204,
    )
    def close_position(
        portfolio_id: str,
        asset_code: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> None:
        """Delete every operation of ``asset_code`` plus the positions row."""
        require_portfolio(portfolio_id, db)
        lifecycle = _build_position_lifecycle_service(db)
        lifecycle.close_position(portfolio_id, asset_code)

    @app.post(
        "/api/portfolios/{portfolio_id}/operations",
        response_model=None,
        status_code=201,
    )
    def create_operation(
        portfolio_id: str,
        payload: OperationCreate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> dict[str, Any]:
        require_portfolio(portfolio_id, db)
        fields = _to_snake_payload(payload, _OPERATION_CREATE_FIELD_MAP)
        lifecycle = _build_position_lifecycle_service(db)
        try:
            return lifecycle.create_operation(portfolio_id, fields)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch(
        "/api/portfolios/{portfolio_id}/operations/{operation_id}",
        response_model=None,
    )
    def update_operation(
        portfolio_id: str,
        operation_id: int,
        payload: OperationUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> dict[str, Any]:
        require_portfolio(portfolio_id, db)
        fields = _to_snake_payload(payload, _OPERATION_FIELD_MAP)
        if not fields:
            raise HTTPException(status_code=422, detail="No fields to update")
        lifecycle = _build_position_lifecycle_service(db)
        try:
            return lifecycle.update_operation(portfolio_id, operation_id, fields)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete(
        "/api/portfolios/{portfolio_id}/operations/{operation_id}",
        status_code=204,
    )
    def delete_operation(
        portfolio_id: str,
        operation_id: int,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> None:
        require_portfolio(portfolio_id, db)
        lifecycle = _build_position_lifecycle_service(db)
        try:
            lifecycle.delete_operation(portfolio_id, operation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ------------------------------------------------------------------
    # Previdencia snapshot CRUD
    # ------------------------------------------------------------------

    @app.patch(
        "/api/portfolios/{portfolio_id}/previdencia/{asset_code}",
        response_model=None,
    )
    def update_previdencia_snapshot(
        portfolio_id: str,
        asset_code: str,
        payload: PrevidenciaSnapshotUpdate,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> dict[str, Any]:
        require_portfolio(portfolio_id, db)
        repo = PrevidenciaSnapshotRepository(db.connection)
        current = repo.get_by_asset(portfolio_id, asset_code)
        if current is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        fields = _to_snake_payload(payload, _PREVIDENCIA_FIELD_MAP)
        if not fields:
            raise HTTPException(status_code=422, detail="No fields to update")
        repo.update(portfolio_id, asset_code, fields)
        updated = repo.get_by_asset(portfolio_id, asset_code)
        if updated is None:  # pragma: no cover - defensive
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return {
            "id": updated.id,
            "portfolioId": updated.portfolio_id,
            "assetCode": updated.asset_code,
            "productName": updated.product_name,
            "quantity": updated.quantity,
            "unitPriceCents": updated.unit_price_cents,
            "marketValueCents": updated.market_value_cents,
            "periodMonth": updated.period_month,
            "periodStartDate": updated.period_start_date,
            "periodEndDate": updated.period_end_date,
        }

    @app.delete(
        "/api/portfolios/{portfolio_id}/previdencia/{asset_code}",
        status_code=204,
    )
    def delete_previdencia_snapshot(
        portfolio_id: str,
        asset_code: str,
        db: Database = Depends(get_db),  # noqa: B008
    ) -> None:
        require_portfolio(portfolio_id, db)
        repo = PrevidenciaSnapshotRepository(db.connection)
        if repo.get_by_asset(portfolio_id, asset_code) is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        repo.delete(portfolio_id, asset_code)

    return app


app = create_http_app()
