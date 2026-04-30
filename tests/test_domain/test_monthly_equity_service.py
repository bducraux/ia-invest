"""Tests for the monthly equity curve service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.models import Operation, Portfolio
from domain.monthly_equity_service import MonthlyEquityService
from domain.previdencia import PrevidenciaSnapshot
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository


@dataclass
class _StubFxRow:
    pass


class _StubFxRepo:
    """Minimal FX repo stub — only used when international assets exist."""

    def get_latest_on_or_before(self, pair, rate_date):  # noqa: ANN001
        return None


class _StubHistoricalPriceService:
    """Returns a fixed close per asset; never hits the network."""

    def __init__(self, prices: dict[str, int]) -> None:
        # ``prices`` maps asset_code → close_cents (always BRL).
        self._prices = prices

    def backfill(self, asset_code, asset_type, start_date, end_date):  # noqa: ANN001
        class _R:
            rows_inserted = 0
            coverage_start = None
            coverage_end = None
            source = "stub"

        return _R()

    def get_close_on_or_before(self, asset_code, asset_type, rate_date):  # noqa: ANN001
        cents = self._prices.get(asset_code.upper())
        if cents is None:
            return None
        return cents, "BRL", "stub"


def _seed_portfolio(tmp_db, portfolio_id: str = "rv") -> None:
    PortfolioRepository(tmp_db.connection).upsert(
        Portfolio(
            id=portfolio_id,
            name=portfolio_id.upper(),
            base_currency="BRL",
            status="active",
        )
    )


def _make_op(
    portfolio_id: str,
    asset_code: str,
    operation_type: str,
    operation_date: str,
    quantity: float,
    unit_price_cents: int,
    *,
    external_id: str | None = None,
) -> Operation:
    gross = int(round(quantity * unit_price_cents))
    return Operation(
        portfolio_id=portfolio_id,
        source="test",
        external_id=external_id or f"{asset_code}-{operation_type}-{operation_date}-{quantity}",
        asset_code=asset_code,
        asset_type="stock",
        operation_type=operation_type,
        operation_date=operation_date,
        quantity=quantity,
        unit_price=unit_price_cents,
        gross_value=gross,
        fees=0,
    )


def test_monthly_equity_curve_basic_renda_variavel(tmp_db) -> None:
    _seed_portfolio(tmp_db, "rv")
    op_repo = OperationRepository(tmp_db.connection)
    op_repo.insert_many(
        [
            _make_op("rv", "PETR4", "buy", "2024-02-10", 100, 3000),  # R$ 30,00
            _make_op("rv", "PETR4", "buy", "2024-03-15", 50, 3200),  # R$ 32,00
        ]
    )

    hist = _StubHistoricalPriceService({"PETR4": 3500})  # R$ 35,00
    service = MonthlyEquityService(
        tmp_db,
        historical_prices=hist,  # type: ignore[arg-type]
        fx_repo=_StubFxRepo(),  # type: ignore[arg-type]
    )

    points = service.compute(["rv"], "2024-02", "2024-04")

    assert [p.month for p in points] == ["2024-02", "2024-03", "2024-04"]
    # Feb: 100 shares * R$35 = R$ 3500,00 → 350000 cents
    assert points[0].market_value_cents == 100 * 3500
    # Mar: 150 shares * R$35 = R$ 5250,00
    assert points[1].market_value_cents == 150 * 3500
    # Apr: 150 shares * R$35 (no new ops)
    assert points[2].market_value_cents == 150 * 3500

    # In-month contributions
    assert points[0].net_contributions_cents == 100 * 3000
    assert points[1].net_contributions_cents == 50 * 3200
    assert points[2].net_contributions_cents == 0

    # Cumulative contributions monotonically increasing
    assert (
        points[0].cumulative_contributions_cents
        <= points[1].cumulative_contributions_cents
        <= points[2].cumulative_contributions_cents
    )
    assert points[2].cumulative_contributions_cents == 100 * 3000 + 50 * 3200

    # Single-class breakdown matches total
    for p in points:
        assert p.breakdown_by_class.get("renda-variavel") == p.market_value_cents


def test_monthly_equity_curve_includes_previdencia_history(tmp_db) -> None:
    _seed_portfolio(tmp_db, "prev")
    prev_repo = PrevidenciaSnapshotRepository(tmp_db.connection)
    # Two snapshots in different months.
    prev_repo.upsert_if_newer(
        PrevidenciaSnapshot(
            portfolio_id="prev",
            asset_code="PGBL_X",
            product_name="PGBL X",
            quantity=10.0,
            unit_price_cents=10000,
            market_value_cents=100000,
            period_month="2024-02",
        )
    )
    prev_repo.upsert_if_newer(
        PrevidenciaSnapshot(
            portfolio_id="prev",
            asset_code="PGBL_X",
            product_name="PGBL X",
            quantity=11.0,
            unit_price_cents=12000,
            market_value_cents=132000,
            period_month="2024-04",
        )
    )

    hist = _StubHistoricalPriceService({})
    service = MonthlyEquityService(
        tmp_db,
        historical_prices=hist,  # type: ignore[arg-type]
        fx_repo=_StubFxRepo(),  # type: ignore[arg-type]
    )

    points = service.compute(["prev"], "2024-02", "2024-05")
    months = {p.month: p for p in points}
    # Feb uses Feb snapshot; Mar still uses Feb (most-recent ≤ Mar);
    # Apr/May use Apr snapshot.
    assert months["2024-02"].market_value_cents == 100000
    assert months["2024-03"].market_value_cents == 100000
    assert months["2024-04"].market_value_cents == 132000
    assert months["2024-05"].market_value_cents == 132000

    for p in points:
        assert p.breakdown_by_class.get("previdencia") == p.market_value_cents


def test_monthly_equity_curve_warns_on_missing_quote(tmp_db) -> None:
    _seed_portfolio(tmp_db, "rv")
    OperationRepository(tmp_db.connection).insert_many(
        [_make_op("rv", "MISS4", "buy", "2024-02-10", 10, 1000)]
    )

    hist = _StubHistoricalPriceService({})  # no price for MISS4
    service = MonthlyEquityService(
        tmp_db,
        historical_prices=hist,  # type: ignore[arg-type]
        fx_repo=_StubFxRepo(),  # type: ignore[arg-type]
    )
    points = service.compute(["rv"], "2024-02", "2024-02")

    assert points[0].market_value_cents == 0
    assert any(w.startswith("sem-cotacao:") for w in points[0].warnings)


def test_monthly_equity_curve_uses_today_when_to_month_omitted(tmp_db) -> None:
    """Smoke test: empty portfolio with no operations returns empty series gracefully."""
    _seed_portfolio(tmp_db, "rv")
    hist = _StubHistoricalPriceService({})
    service = MonthlyEquityService(
        tmp_db,
        historical_prices=hist,  # type: ignore[arg-type]
        fx_repo=_StubFxRepo(),  # type: ignore[arg-type]
    )
    today = date.today()
    points = service.compute(
        ["rv"],
        f"{today.year:04d}-{today.month:02d}",
        f"{today.year:04d}-{today.month:02d}",
    )
    assert len(points) == 1
    assert points[0].market_value_cents == 0
    assert points[0].breakdown_by_class == {}
