"""Monthly equity curve — patrimônio mensal across all asset classes.

Walks month-by-month between ``from_month`` and ``to_month`` (inclusive),
replaying operations, valuating fixed-income at month-end via
:class:`FixedIncomeValuationService`, and reading per-month previdência
snapshots via :meth:`PrevidenciaSnapshotRepository.get_at_or_before`.

For each historical date the service uses the cached close from
:class:`HistoricalPriceService`. International / crypto closes in USD/USDT
are converted to BRL using the FX rate cached at the same as-of date.

All monetary outputs are integers in cents.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from domain.fixed_income_rates import DailyRateProvider, FlatCDIRateProvider
from domain.fixed_income_valuation import FixedClock, FixedIncomeValuationService
from mcp_server.services.historical_prices import HistoricalPriceService
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.fx_rates import FxRatesRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository

# Asset types that fall under each class for breakdown.
_RV_TYPES = {"stock", "fii", "etf", "bdr", "bond"}
_INT_TYPES = {"stock_us", "etf_us", "reit_us", "bdr_us"}
_CRYPTO_TYPES = {"crypto"}

_BUY_TYPES = {"buy", "transfer_in", "split_bonus"}
_SELL_TYPES = {"sell", "transfer_out"}
_INCOME_TYPES = {"dividend", "jcp", "rendimento", "amortization"}


def _last_day_of_month(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


def _iter_months(from_month: str, to_month: str) -> list[date]:
    start_y, start_m = (int(p) for p in from_month.split("-"))
    end_y, end_m = (int(p) for p in to_month.split("-"))
    out: list[date] = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        out.append(_last_day_of_month(y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


@dataclass
class EquityPoint:
    month: str  # YYYY-MM
    as_of_date: str  # YYYY-MM-DD (month end)
    market_value_cents: int = 0
    breakdown_by_class: dict[str, int] = field(default_factory=dict)
    net_contributions_cents: int = 0  # In-month contributions (buys - sells)
    # Cost basis of open positions at month_end + principal of active RFs.
    # Mirrors the "Total investido" KPI in the overview.
    cumulative_contributions_cents: int = 0
    dividends_received_cents: int = 0  # In-month income
    warnings: list[str] = field(default_factory=list)


class MonthlyEquityService:
    """Compute the monthly equity curve for one or more portfolios."""

    def __init__(
        self,
        db: Database,
        *,
        historical_prices: HistoricalPriceService,
        fx_repo: FxRatesRepository,
        cdi_provider: DailyRateProvider | None = None,
    ) -> None:
        self._db = db
        self._hist = historical_prices
        self._fx = fx_repo
        self._cdi = cdi_provider or FlatCDIRateProvider(0)

    def compute(
        self,
        portfolio_ids: list[str],
        from_month: str,
        to_month: str,
    ) -> list[EquityPoint]:
        """Return one :class:`EquityPoint` per month in ``[from_month, to_month]``.

        ``portfolio_ids`` lets the caller aggregate across portfolios
        (consolidated view).
        """
        op_repo = OperationRepository(self._db.connection)
        rf_repo = FixedIncomePositionRepository(self._db.connection)
        prev_repo = PrevidenciaSnapshotRepository(self._db.connection)

        # 1) Collect all operations once.
        all_ops: list[dict[str, Any]] = []
        for pid in portfolio_ids:
            all_ops.extend(op_repo.list_all_by_portfolio(pid))
        all_ops.sort(key=lambda o: (o["operation_date"], o["id"]))

        # 2) Pre-warm the historical price cache for every distinct asset
        #    in operations that needs market quotes.
        needed: dict[str, str] = {}
        for op in all_ops:
            atype = (op.get("asset_type") or "").lower()
            if atype in _RV_TYPES | _INT_TYPES | _CRYPTO_TYPES:
                needed.setdefault(op["asset_code"], atype)
        if all_ops and needed:
            first_op_date = datetime.strptime(all_ops[0]["operation_date"], "%Y-%m-%d").date()
            backfill_start = date(first_op_date.year, max(1, first_op_date.month - 1), 1)
            backfill_end = max(date.today(), _iter_months(from_month, to_month)[-1])
            for code, atype in needed.items():
                self._hist.backfill(code, atype, backfill_start, backfill_end)

        # 3) Index RF positions and previdência snapshots.
        rf_positions = []
        for pid in portfolio_ids:
            rf_positions.extend(rf_repo.list_by_portfolio(pid))

        prev_history: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for pid in portfolio_ids:
            for snap in prev_repo.list_history(pid):
                prev_history[(pid, snap.asset_code)].append(snap)

        prev_assets: list[tuple[str, str]] = sorted({k for k in prev_history})

        # 4) Walk months.
        months = _iter_months(from_month, to_month)
        points: list[EquityPoint] = []

        # Operations are pre-sorted; track index to compute in-month contributions.
        for month_end in months:
            month_str = f"{month_end.year:04d}-{month_end.month:02d}"
            month_start = date(month_end.year, month_end.month, 1)
            in_month_contrib = 0
            in_month_dividends = 0

            # Replay quantities AND running cost basis up to month_end. Mirrors
            # PositionService: on a sell, total_cost is reduced proportionally to
            # the share of quantity sold.
            qty_by_asset: dict[tuple[str, str], float] = defaultdict(float)
            cost_by_asset: dict[tuple[str, str], int] = defaultdict(int)
            asset_type_of: dict[tuple[str, str], str] = {}
            warnings: set[str] = set()
            for op in all_ops:
                op_date = datetime.strptime(op["operation_date"], "%Y-%m-%d").date()
                if op_date > month_end:
                    break
                key = (op["portfolio_id"], op["asset_code"])
                atype = (op.get("asset_type") or "").lower()
                asset_type_of[key] = atype
                op_type = op["operation_type"]
                qty = op["quantity"]
                gross = int(op["gross_value"])
                fees = int(op["fees"])
                if op_type in _BUY_TYPES:
                    cost_by_asset[key] += gross + fees
                    qty_by_asset[key] += qty
                elif op_type in _SELL_TYPES:
                    current_qty = qty_by_asset[key]
                    if current_qty > 0:
                        cost_sold = int(
                            (
                                Decimal(cost_by_asset[key])
                                * Decimal(str(qty))
                                / Decimal(str(current_qty))
                            ).to_integral_value()
                        )
                        cost_by_asset[key] -= cost_sold
                    qty_by_asset[key] -= qty
                # In-month metrics
                if month_start <= op_date <= month_end:
                    if op_type in _BUY_TYPES:
                        in_month_contrib += gross + fees
                    elif op_type in _SELL_TYPES:
                        in_month_contrib -= gross - fees
                    elif op_type in _INCOME_TYPES:
                        in_month_dividends += gross - fees

            # Value renda variável / internacional / cripto positions.
            breakdown: dict[str, int] = defaultdict(int)
            total_value = 0
            for (pid, asset_code), qty in qty_by_asset.items():
                if qty <= 0:
                    continue
                atype = asset_type_of.get((pid, asset_code), "")
                bucket = self._classify(atype)
                if bucket == "other":
                    continue
                value_cents = self._value_at(asset_code, atype, month_end, qty)
                if value_cents is None:
                    warnings.add(f"sem-cotacao:{asset_code}")
                    continue
                breakdown[bucket] += value_cents
                total_value += value_cents

            # Value renda-fixa positions as of month_end.
            valuation_service = FixedIncomeValuationService(
                cdi_provider=self._cdi, clock=FixedClock(month_end)
            )
            rf_value = 0
            rf_invested = 0
            for pos in rf_positions:
                applied: date | None = None
                if pos.application_date:
                    applied = datetime.strptime(pos.application_date, "%Y-%m-%d").date()
                    if applied > month_end:
                        continue
                valuation = valuation_service.revalue_as_of(pos, month_end)
                rf_value += int(valuation.net_value_current_brl or valuation.gross_value_current_brl or 0)
                if not valuation.is_complete:
                    warnings.add(f"rf-incompleta:{pos.id}")
                # Match the KPI: principal counts toward total_invested only
                # while the RF is active (applied and not yet matured).
                matured = False
                if pos.maturity_date:
                    maturity = datetime.strptime(pos.maturity_date, "%Y-%m-%d").date()
                    if maturity <= month_end:
                        matured = True
                if not matured:
                    rf_invested += int(pos.principal_applied_brl or 0)
            if rf_value:
                breakdown["renda-fixa"] += rf_value
                total_value += rf_value

            # Value previdência using as-of-or-before snapshots.
            prev_value = 0
            for pid, asset_code in prev_assets:
                prev_snap = prev_repo.get_at_or_before(pid, asset_code, month_str)
                if prev_snap is None:
                    continue
                prev_value += int(prev_snap.market_value_cents)
            if prev_value:
                breakdown["previdencia"] += prev_value
                total_value += prev_value

            # Total invested at month_end mirrors the "Total investido" KPI:
            # cost basis of open positions (RV/cripto/internacional) plus the
            # principal of active RFs. Previdência has no historical cost.
            total_invested_at_month_end = sum(
                cost
                for key, cost in cost_by_asset.items()
                if qty_by_asset[key] > 0
            ) + rf_invested

            points.append(
                EquityPoint(
                    month=month_str,
                    as_of_date=month_end.isoformat(),
                    market_value_cents=total_value,
                    breakdown_by_class=dict(breakdown),
                    net_contributions_cents=in_month_contrib,
                    cumulative_contributions_cents=total_invested_at_month_end,
                    dividends_received_cents=in_month_dividends,
                    warnings=sorted(warnings),
                )
            )

        return points

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _classify(self, asset_type: str) -> str:
        if asset_type in _RV_TYPES:
            return "renda-variavel"
        if asset_type in _INT_TYPES:
            return "internacional"
        if asset_type in _CRYPTO_TYPES:
            return "cripto"
        return "other"

    def _value_at(
        self,
        asset_code: str,
        asset_type: str,
        as_of: date,
        quantity: float,
    ) -> int | None:
        cached = self._hist.get_close_on_or_before(asset_code, asset_type, as_of)
        if cached is None:
            return None
        close_cents, currency, _ = cached
        # Convert non-BRL closes to BRL using the FX cache as-of the same date.
        if currency.upper() not in {"BRL", ""}:
            pair = f"{currency.upper()}BRL" if currency.upper() != "USDT" else "USDBRL"
            fx = self._fx.get_latest_on_or_before(pair, as_of)
            if fx is None:
                return None
            _, rate, _ = fx
            value = (
                Decimal(close_cents)
                * Decimal(str(quantity))
                * rate
            )
            return int(value.to_integral_value())
        value = Decimal(close_cents) * Decimal(str(quantity))
        return int(value.to_integral_value())


def equity_curve_to_payload(
    portfolio_ids: list[str],
    points: list[EquityPoint],
) -> dict[str, Any]:
    """Serialise into a JSON-friendly payload for MCP/HTTP consumers."""
    return {
        "portfolio_ids": portfolio_ids,
        "from_month": points[0].month if points else None,
        "to_month": points[-1].month if points else None,
        "series": [
            {
                "month": p.month,
                "as_of_date": p.as_of_date,
                "market_value_cents": p.market_value_cents,
                "breakdown_by_class": p.breakdown_by_class,
                "net_contributions_cents": p.net_contributions_cents,
                "cumulative_contributions_cents": p.cumulative_contributions_cents,
                "dividends_received_cents": p.dividends_received_cents,
                "warnings": p.warnings,
            }
            for p in points
        ],
    }


def build_default_service(db: Database) -> MonthlyEquityService:
    """Wire a service with the standard production dependencies."""
    repo = BenchmarkRatesRepository(db.connection)
    _, _, count = repo.get_coverage("CDI")
    cdi = (
        __import__("domain.fixed_income_rates", fromlist=["SQLiteDailyRateProvider"]).SQLiteDailyRateProvider(repo)
        if count > 0
        else FlatCDIRateProvider(0)
    )
    from storage.repository.historical_prices import HistoricalPricesRepository

    hist_repo = HistoricalPricesRepository(db.connection)
    hist_service = HistoricalPriceService(hist_repo)
    fx_repo = FxRatesRepository(db.connection)
    return MonthlyEquityService(
        db,
        historical_prices=hist_service,
        fx_repo=fx_repo,
        cdi_provider=cdi,
    )


def list_known_portfolio_ids(db: Database) -> list[str]:
    return [p.id for p in PortfolioRepository(db.connection).list_all()]
