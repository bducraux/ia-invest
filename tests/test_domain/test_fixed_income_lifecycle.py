from __future__ import annotations

from datetime import date

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_valuation import FixedIncomeValuationService
from domain.models import Portfolio
from mcp_server.services.fixed_income_lifecycle import FixedIncomeLifecycleService
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.portfolios import PortfolioRepository


def _seed_portfolio(repo: PortfolioRepository) -> None:
    repo.upsert(
        Portfolio(
            id="rf-portfolio",
            name="RF",
            base_currency="BRL",
            status="active",
        )
    )


def _position() -> FixedIncomePosition:
    return FixedIncomePosition(
        portfolio_id="rf-portfolio",
        institution="Banco X",
        asset_type="CDB",
        product_name="CDB Teste",
        remuneration_type="PRE",
        benchmark="NONE",
        investor_type="PF",
        currency="BRL",
        application_date="2024-01-01",
        maturity_date="2024-01-11",
        principal_applied_brl=1_000_000,
        fixed_rate_annual_percent=10.0,
    )


def test_redeem_creates_new_and_deletes_old(tmp_db) -> None:
    """Redeem reinvests proceeds: old row is deleted, new row is ACTIVE."""
    _seed_portfolio(PortfolioRepository(tmp_db.connection))
    repo = FixedIncomePositionRepository(tmp_db.connection)
    valuation = FixedIncomeValuationService()
    service = FixedIncomeLifecycleService(repo, valuation)

    original = _position()
    original_id = repo.insert(original)

    expected = valuation.revalue_as_of(original, as_of=date(2024, 1, 15))
    replacement = service.redeem("rf-portfolio", original_id, as_of_date="2024-01-15")

    # Old row must be gone.
    assert repo.get(original_id) is None

    # New row has correct fields.
    assert replacement.id is not None
    assert replacement.id != original_id
    assert replacement.status == "ACTIVE"
    assert replacement.application_date == "2024-01-15"
    assert replacement.maturity_date == "2024-01-25"
    assert replacement.principal_applied_brl == expected.net_value_current_brl


def test_close_deletes_position(tmp_db) -> None:
    """Close simply removes the row with no new position created."""
    _seed_portfolio(PortfolioRepository(tmp_db.connection))
    repo = FixedIncomePositionRepository(tmp_db.connection)
    service = FixedIncomeLifecycleService(repo, FixedIncomeValuationService())

    pos = _position()
    pos_id = repo.insert(pos)

    service.close("rf-portfolio", pos_id)

    assert repo.get(pos_id) is None
    assert repo.list_by_portfolio("rf-portfolio") == []


def test_auto_reapply_reconciles_idempotently(tmp_db) -> None:
    """reconcile_auto_reapply runs redeem once; second call finds nothing."""
    _seed_portfolio(PortfolioRepository(tmp_db.connection))
    repo = FixedIncomePositionRepository(tmp_db.connection)
    service = FixedIncomeLifecycleService(repo, FixedIncomeValuationService())

    original = _position()
    original.auto_reapply_enabled = True
    original_id = repo.insert(original)

    first = service.reconcile_auto_reapply("rf-portfolio", as_of_date="2024-01-15")
    second = service.reconcile_auto_reapply("rf-portfolio", as_of_date="2024-01-15")

    assert first == 1
    assert second == 0

    # Original is gone, exactly one new position exists.
    assert repo.get(original_id) is None
    positions = repo.list_by_portfolio("rf-portfolio")
    assert len(positions) == 1
    assert positions[0].auto_reapply_enabled is True
    assert positions[0].status == "ACTIVE"


def test_auto_reapply_zero_duration_uses_minimum_one_day(tmp_db) -> None:
    """Auto-reapply must not keep a same-day maturity that loops on every read."""
    _seed_portfolio(PortfolioRepository(tmp_db.connection))
    repo = FixedIncomePositionRepository(tmp_db.connection)
    service = FixedIncomeLifecycleService(repo, FixedIncomeValuationService())

    original = _position()
    original.application_date = "2024-01-10"
    original.maturity_date = "2024-01-10"
    original.auto_reapply_enabled = True
    original_id = repo.insert(original)

    first = service.reconcile_auto_reapply("rf-portfolio", as_of_date="2024-01-15")
    second = service.reconcile_auto_reapply("rf-portfolio", as_of_date="2024-01-15")

    assert first == 1
    assert second == 0
    assert repo.get(original_id) is None

    positions = repo.list_by_portfolio("rf-portfolio")
    assert len(positions) == 1
    assert positions[0].application_date == "2024-01-15"
    assert positions[0].maturity_date == "2024-01-16"


def test_auto_reapply_preserves_span_when_dates_are_inverted(tmp_db) -> None:
    """If dates are inverted by manual edit, reapply keeps the same day-span magnitude."""
    _seed_portfolio(PortfolioRepository(tmp_db.connection))
    repo = FixedIncomePositionRepository(tmp_db.connection)
    service = FixedIncomeLifecycleService(repo, FixedIncomeValuationService())

    original = _position()
    original.application_date = "2024-02-01"
    original.maturity_date = "2024-01-01"  # 31-day span, inverted.
    original.auto_reapply_enabled = True
    repo.insert(original)

    count = service.reconcile_auto_reapply("rf-portfolio", as_of_date="2024-03-01")

    assert count == 1
    positions = repo.list_by_portfolio("rf-portfolio")
    assert len(positions) == 1
    assert positions[0].application_date == "2024-03-01"
    assert positions[0].maturity_date == "2024-04-01"
