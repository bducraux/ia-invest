from __future__ import annotations

from domain.models import Portfolio
from domain.previdencia import PrevidenciaSnapshot
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository


def _seed_portfolio(tmp_db) -> None:
    PortfolioRepository(tmp_db.connection).upsert(
        Portfolio(
            id="p1",
            name="P1",
            base_currency="BRL",
            status="active",
        )
    )


def test_upsert_if_newer_inserts_each_distinct_period(tmp_db) -> None:
    _seed_portfolio(tmp_db)
    repo = PrevidenciaSnapshotRepository(tmp_db.connection)

    newer = PrevidenciaSnapshot(
        portfolio_id="p1",
        asset_code="PREV_IBM_CD",
        product_name="IBM CD",
        quantity=10.0,
        unit_price_cents=1000,
        market_value_cents=10000,
        period_month="2026-03",
    )
    older = PrevidenciaSnapshot(
        portfolio_id="p1",
        asset_code="PREV_IBM_CD",
        product_name="IBM CD",
        quantity=9.0,
        unit_price_cents=900,
        market_value_cents=8100,
        period_month="2026-02",
    )

    assert repo.upsert_if_newer(newer) == "inserted"
    # Older periods are now also persisted (history-aware behaviour).
    assert repo.upsert_if_newer(older) == "inserted"

    # get_by_asset returns the latest period.
    current = repo.get_by_asset("p1", "PREV_IBM_CD")
    assert current is not None
    assert current.period_month == "2026-03"
    assert current.unit_price_cents == 1000

    history = repo.list_history("p1", "PREV_IBM_CD")
    assert [s.period_month for s in history] == ["2026-02", "2026-03"]


def test_upsert_if_newer_updates_same_period(tmp_db) -> None:
    _seed_portfolio(tmp_db)
    repo = PrevidenciaSnapshotRepository(tmp_db.connection)

    first = PrevidenciaSnapshot(
        portfolio_id="p1",
        asset_code="PREV_IBM_CD",
        product_name="IBM CD",
        quantity=10.0,
        unit_price_cents=1000,
        market_value_cents=10000,
        period_month="2026-03",
    )
    second = PrevidenciaSnapshot(
        portfolio_id="p1",
        asset_code="PREV_IBM_CD",
        product_name="IBM CD",
        quantity=11.0,
        unit_price_cents=1100,
        market_value_cents=12100,
        period_month="2026-03",
    )

    assert repo.upsert_if_newer(first) == "inserted"
    assert repo.upsert_if_newer(second) == "updated"

    current = repo.get_by_asset("p1", "PREV_IBM_CD")
    assert current is not None
    assert current.quantity == 11.0
    assert current.unit_price_cents == 1100
