"""Stepwise scenario tests for wallet state reconciliation.

Each scenario imports multiple CSV files in steps and validates positions
after each step to ensure wallet (positions table) is updated correctly.

Focus: quantity, avg_price, total_cost (ignore realized_pnl, dividends for crypto).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.portfolio_service import PortfolioService
from domain.position_service import PositionService
from extractors import get_extractor
from normalizers.operations import OperationNormalizer
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _assert_position(
    pos: dict[str, object] | None,
    asset_code: str,
    expected_quantity: float,
    expected_avg_price: int | None = None,
    expected_total_cost: int | None = None,
) -> None:
    """Assert a position matches expected values (crypto-focused, ignore P&L)."""
    assert pos is not None, f"Position for {asset_code} not found"
    assert pos["asset_code"] == asset_code
    assert float(pos["quantity"]) == pytest.approx(expected_quantity, rel=1e-6), \
        f"{asset_code}: expected qty={expected_quantity}, got {pos['quantity']}"
    
    if expected_avg_price is not None:
        assert pos["avg_price"] == expected_avg_price, \
            f"{asset_code}: expected avg_price={expected_avg_price}, got {pos['avg_price']}"
    
    if expected_total_cost is not None:
        assert pos["total_cost"] == expected_total_cost, \
            f"{asset_code}: expected total_cost={expected_total_cost}, got {pos['total_cost']}"


def _import_step(
    db: Database,
    portfolio_id: str,
    csv_path: Path,
) -> None:
    """Import a single CSV step and recompute positions."""
    extractor = get_extractor("binance_csv")
    if not extractor.can_handle(csv_path):
        raise ValueError(f"Cannot handle {csv_path}")
    
    extraction = extractor.extract(csv_path)
    normalizer = OperationNormalizer()
    norm = normalizer.normalize(extraction.records, portfolio_id)
    
    op_repo = OperationRepository(db.connection)
    op_repo.insert_many(norm.valid)
    
    all_ops = op_repo.list_all_by_portfolio(portfolio_id)
    pos_svc = PositionService()
    positions = pos_svc.calculate(all_ops, portfolio_id)
    
    pos_repo = PositionRepository(db.connection)
    pos_repo.upsert_many(positions)


@pytest.fixture
def test_scenario_db(tmp_path: Path) -> Database:
    """Provide a fresh test database."""
    db = Database(tmp_path / "scenario.db")
    db.initialize()
    return db


@pytest.fixture
def portfolio_cripto(test_scenario_db: Database) -> str:
    """Register a crypto portfolio."""
    portfolio = PortfolioService().load_from_yaml(
        Path("templates/cripto/portfolio.yml")
    )
    PortfolioRepository(test_scenario_db.connection).upsert(portfolio)
    return portfolio.id


def test_scenario_brl_pairs_buy_and_sell(
    test_scenario_db: Database, portfolio_cripto: str
) -> None:
    """Scenario: Buy BTC with BRL, then sell partial BTC."""
    csv_dir = Path("tests/test_data")
    
    # Step 1: Buy 0.05 BTC for 5000 BRL
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_brl_pairs_step_01.csv")
    
    pos_repo = PositionRepository(test_scenario_db.connection)
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    _assert_position(positions.get("BTC"), "BTC", 0.05, expected_avg_price=10000000)
    assert "BRL" not in positions, "BRL should not appear in positions"
    
    # Step 2: Sell 0.02 BTC for 2100 BRL
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_brl_pairs_step_02.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # 0.05 - 0.02 = 0.03 BTC remaining
    _assert_position(positions.get("BTC"), "BTC", 0.03, expected_avg_price=10000000)


def test_scenario_usdt_quote_pairs(
    test_scenario_db: Database, portfolio_cripto: str
) -> None:
    """Scenario: Buy USDT with BRL, buy BTC with USDT, sell BTC to USDT."""
    csv_dir = Path("tests/test_data")
    
    # Step 1: Buy 1000 USDT for 5000 BRL
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_usdt_pairs_step_01.csv")
    
    pos_repo = PositionRepository(test_scenario_db.connection)
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    _assert_position(positions.get("USDT"), "USDT", 1000.0, expected_avg_price=500)
    assert "BRL" not in positions
    
    # Step 2: Buy 0.005 BTC with 300 USDT (quote leg deducts USDT)
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_usdt_pairs_step_02.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # USDT: 1000 - 300 = 700 (spent on BTC quote leg)
    _assert_position(positions.get("USDT"), "USDT", 700.0)
    # BTC: 0.005 bought
    _assert_position(positions.get("BTC"), "BTC", 0.005, expected_avg_price=6000000)
    
    # Step 3: Sell 0.001 BTC for 65 USDT (quote leg adds USDT)
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_usdt_pairs_step_03.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # BTC: 0.005 - 0.001 = 0.004 remaining
    _assert_position(positions.get("BTC"), "BTC", 0.004, expected_avg_price=6000000)
    # USDT: 700 + 65 = 765 (received from sell)
    _assert_position(positions.get("USDT"), "USDT", 765.0)


def test_scenario_cross_crypto_pairs(
    test_scenario_db: Database, portfolio_cripto: str
) -> None:
    """Scenario: Buy BTC with BRL, buy ETH with BTC, buy BTC with ETH."""
    csv_dir = Path("tests/test_data")
    
    # Step 1: Buy 0.1 BTC with BRL
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_cross_crypto_step_01.csv")
    
    pos_repo = PositionRepository(test_scenario_db.connection)
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    _assert_position(positions.get("BTC"), "BTC", 0.1, expected_avg_price=10000000)
    
    # Step 2: Buy 1 ETH with 0.05 BTC (quote leg deducts BTC)
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_cross_crypto_step_02.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # BTC: 0.1 - 0.05 = 0.05 remaining
    _assert_position(positions.get("BTC"), "BTC", 0.05, expected_avg_price=10000000)
    # ETH: 1 bought at 0.05 BTC price (would need cross-rate normalization for avg_price in BRL)
    _assert_position(positions.get("ETH"), "ETH", 1.0)
    
    # Step 3: Buy 0.02 BTC with 20 ETH
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_cross_crypto_step_03.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # ETH: 1 - 20 = -19 (temporary negative, no clamp)
    _assert_position(positions.get("ETH"), "ETH", -19.0)
    # BTC: 0.05 + 0.02 = 0.07
    _assert_position(positions.get("BTC"), "BTC", 0.07)


def test_scenario_historical_gap_no_clamp(
    test_scenario_db: Database, portfolio_cripto: str
) -> None:
    """Scenario: Spend USDT before buy USDT appears in history."""
    csv_dir = Path("tests/test_data")
    
    # Step 1: Buy 0.005 BTC with 300 USDT (spends USDT first)
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_historical_gap_step_01.csv")
    
    pos_repo = PositionRepository(test_scenario_db.connection)
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # USDT: -300 (no clamp to zero)
    _assert_position(positions.get("USDT"), "USDT", -300.0)
    # BTC: 0.005
    _assert_position(positions.get("BTC"), "BTC", 0.005, expected_avg_price=6000000)
    
    # Step 2: Buy 500 USDT with BRL (historical gap filled)
    _import_step(test_scenario_db, portfolio_cripto, csv_dir / "scenario_historical_gap_step_02.csv")
    
    positions = {p["asset_code"]: p for p in pos_repo.list_by_portfolio(portfolio_cripto)}
    
    # USDT: -300 + 500 = 200 (arithmetic net preserved)
    _assert_position(positions.get("USDT"), "USDT", 200.0)
    # BTC: still 0.005
    _assert_position(positions.get("BTC"), "BTC", 0.005, expected_avg_price=6000000)
