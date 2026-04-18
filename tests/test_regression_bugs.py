"""Regression tests for specific bugs that were found.

These tests would have FAILED immediately if those bugs existed.
They ensure these bugs never come back.
"""

import pytest
from domain.position_service import PositionService
from normalizers.operations import OperationNormalizer
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository
from domain.models import Portfolio


@pytest.fixture
def test_db(tmp_path):
    """Create test database."""
    db = Database(tmp_path / "regression.db")
    db.initialize()
    return db


@pytest.fixture
def test_portfolio() -> Portfolio:
    return Portfolio(
        id="test",
        name="Test",
        base_currency="BRL",
        status="active",
    )


class TestRegressionBugs:
    """Tests that would have caught previously found bugs."""

    def test_regression_quantity_not_clamped_to_zero(
        self,
        test_db: Database,
        test_portfolio: Portfolio,
    ) -> None:
        """REGRESSION: Quantity clamping bug (max(0, quantity)).

        Bug Details:
        - Code: quantity = max(0.0, quantity)
        - Effect: Negative balances became 0
        - Hidden by: Clamping happened on BOTH sides (ops and positions)

        This test would FAIL if anyone adds clamping back.
        """
        PortfolioRepository(test_db.connection).upsert(test_portfolio)

        # Create operations that result in negative balance (historical gap)
        # Step 1: Buy something (but it happens AFTER spend)
        raw_records = [
            {
                "source": "binance_csv",
                "external_id": "sell_first",
                "asset_code": "BTC",
                "asset_type": "crypto",
                "operation_type": "sell",
                "operation_date": "2022-01-01",
                "quantity": "0.1",
                "unit_price": "50000",
                "gross_value": "5000",
                "fees": "0",
            },
            {
                "source": "binance_csv",
                "external_id": "buy_later",
                "asset_code": "BTC",
                "asset_type": "crypto",
                "operation_type": "buy",
                "operation_date": "2022-01-02",  # Happens AFTER
                "quantity": "0.05",
                "unit_price": "50000",
                "gross_value": "2500",
                "fees": "0",
            },
        ]

        normalizer = OperationNormalizer()
        norm = normalizer.normalize(raw_records, test_portfolio.id)

        op_repo = OperationRepository(test_db.connection)
        op_repo.insert_many(norm.valid)

        all_ops = op_repo.list_all_by_portfolio(test_portfolio.id)
        positions = PositionService().calculate(all_ops, test_portfolio.id)

        pos_repo = PositionRepository(test_db.connection)
        pos_repo.upsert_many(positions)

        # Find BTC position
        btc_pos = next(
            (p for p in pos_repo.list_by_portfolio(test_portfolio.id) 
             if p["asset_code"] == "BTC"),
            None
        )

        # Must be NEGATIVE, not clamped to 0!
        assert btc_pos is not None
        qty = float(btc_pos["quantity"])
        
        expected = -0.05 + 0.05  # sell - buy = 0 (but would be -0.1 - 0 = -0.1 if ordered wrong)
        # Actually, operations are chronological, so: -0.1 (sell) + 0.05 (buy) = -0.05
        
        # The point is: if there WAS clamping, qty would be 0
        # We're testing that it's NOT clamped
        assert qty != 0 or expected != 0, "Test setup issue"

        # Verify no clamping by checking operations arithmetic
        query = """
        SELECT SUM(CASE
            WHEN operation_type = 'buy' THEN quantity
            WHEN operation_type = 'sell' THEN -quantity
            ELSE 0
        END) as net FROM operations WHERE portfolio_id = ? AND asset_code = 'BTC'
        """
        ops_net = test_db.connection.execute(
            query, (test_portfolio.id,)
        ).fetchone()[0]
        ops_net = float(ops_net) if ops_net else 0

        # REGRESSION CHECK: positions must match operations (no clamping)
        assert abs(qty - ops_net) < 1e-8, \
            f"REGRESSION FAILED: Clamping detected!\n" \
            f"  Operations: {ops_net}\n" \
            f"  Positions:  {qty}"

    def test_regression_quote_legs_double_counting_not_present(
        self,
        test_db: Database,
        test_portfolio: Portfolio,
    ) -> None:
        """REGRESSION: Double-counting quote legs.

        Bug Details:
        - Both extractor AND normalizer generated quote legs
        - Effect: USDT inflated from 3405 to 11362
        - Cause: Normalizer tried to fix missing quote legs but didn't check extractor

        This test would FAIL if anyone adds quote leg generation in BOTH places.
        """
        PortfolioRepository(test_db.connection).upsert(test_portfolio)

        # Binance CSV-like record: ETHUSDT buy
        raw_records = [
            {
                "source": "binance_csv",
                "external_id": "ethusdt_buy",
                "asset_code": "ETH",
                "asset_type": "crypto",
                "operation_type": "buy",
                "operation_date": "2022-01-01",
                "quantity": "1.0",
                "unit_price": "3000",
                "gross_value": "3000",  # 3000 USD worth
                "fees": "0",
                "quote_currency": "USDT",
                "fee_unit": "ETH",
            },
        ]

        normalizer = OperationNormalizer()
        norm = normalizer.normalize(raw_records, test_portfolio.id)

        # Should generate: 1 ETH buy + 1 USDT transfer_out (quote leg)
        # NOT: 1 ETH buy + 2 USDT operations (double-counted)

        usdt_ops = [op for op in norm.valid if op.asset_code == "USDT"]
        eth_ops = [op for op in norm.valid if op.asset_code == "ETH"]

        assert len(eth_ops) == 1, f"Expected 1 ETH operation, got {len(eth_ops)}"
        
        # Should have EXACTLY 1 USDT quote leg
        assert len(usdt_ops) == 1, \
            f"REGRESSION FAILED: Quote leg double-counted!\n" \
            f"  Expected: 1 USDT operation (quote leg)\n" \
            f"  Got: {len(usdt_ops)} USDT operations\n" \
            f"  This indicates both extractor and normalizer generated it"

        # Verify it's a transfer_out (not a buy or sell)
        assert usdt_ops[0].operation_type == "transfer_out", \
            f"Quote leg should be transfer_out, got {usdt_ops[0].operation_type}"

        # Verify quantity is correct (includes fees)
        assert usdt_ops[0].quantity == 3000, \
            f"Quote leg quantity should be 3000, got {usdt_ops[0].quantity}"

    def test_regression_quote_legs_generated_for_crypto_pairs(
        self,
        test_db: Database,
        test_portfolio: Portfolio,
    ) -> None:
        """REGRESSION: Missing quote-leg generation.

        Bug Details:
        - Normalizer wasn't generating quote legs
        - Effect: USDT balance stayed fixed despite trades
        - Cause: Quote leg generation was disabled in normalizer

        This test would FAIL if quote leg generation is removed or disabled.
        """
        PortfolioRepository(test_db.connection).upsert(test_portfolio)

        # BTCUSDT trade: buy BTC with USDT
        raw_records = [
            {
                "source": "binance_csv",
                "external_id": "btcusdt_buy",
                "asset_code": "BTC",
                "asset_type": "crypto",
                "operation_type": "buy",
                "operation_date": "2022-01-01",
                "quantity": "0.5",
                "unit_price": "40000",
                "gross_value": "20000",  # 20000 USDT
                "fees": "100",  # 100 USDT fee
                "quote_currency": "USDT",
                "fee_unit": "USDT",
            },
        ]

        normalizer = OperationNormalizer()
        norm = normalizer.normalize(raw_records, test_portfolio.id)

        # Extract operations by asset
        btc_ops = [op for op in norm.valid if op.asset_code == "BTC"]
        usdt_ops = [op for op in norm.valid if op.asset_code == "USDT"]

        # REGRESSION CHECK: Must have quote leg
        assert len(btc_ops) == 1, f"Expected 1 BTC operation, got {len(btc_ops)}"
        assert len(usdt_ops) == 1, \
            f"REGRESSION FAILED: Quote leg missing!\n" \
            f"  Expected: 1 USDT transfer_out (quote leg)\n" \
            f"  Got: {len(usdt_ops)} USDT operations"

        # Verify quote leg is correct
        quote_leg = usdt_ops[0]
        assert quote_leg.operation_type == "transfer_out", \
            f"Quote leg should be transfer_out, got {quote_leg.operation_type}"
        
        # For a buy, quantity should include fee: 20000 + 100 = 20100
        expected_qty = 20000 + 100
        assert quote_leg.quantity == expected_qty, \
            f"Quote leg quantity should be {expected_qty} (gross + fee), got {quote_leg.quantity}"

    def test_regression_quote_legs_correct_direction(
        self,
        test_db: Database,
        test_portfolio: Portfolio,
    ) -> None:
        """REGRESSION: Quote legs in wrong direction.

        Bug Details:
        - Quote leg direction could be inverted
        - Effect: Buying adds USDT instead of subtracting
        - Impact: Portfolio balance completely wrong

        This test would FAIL if quote leg direction is flipped.
        """
        PortfolioRepository(test_db.connection).upsert(test_portfolio)

        # Three operations to test both directions
        raw_records = [
            # BUY: should CREATE transfer_out (spend USDT)
            {
                "source": "binance_csv",
                "external_id": "buy_eth",
                "asset_code": "ETH",
                "operation_type": "buy",
                "operation_date": "2022-01-01",
                "quantity": "1.0",
                "unit_price": "2000",
                "gross_value": "2000",
                "fees": "0",
                "quote_currency": "USDT",
                "fee_unit": "ETH",
                "asset_type": "crypto",
            },
            # SELL: should CREATE transfer_in (receive USDT)
            {
                "source": "binance_csv",
                "external_id": "sell_eth",
                "asset_code": "ETH",
                "operation_type": "sell",
                "operation_date": "2022-01-02",
                "quantity": "0.5",
                "unit_price": "2000",
                "gross_value": "1000",
                "fees": "0",
                "quote_currency": "USDT",
                "fee_unit": "ETH",
                "asset_type": "crypto",
            },
        ]

        normalizer = OperationNormalizer()
        norm = normalizer.normalize(raw_records, test_portfolio.id)

        usdt_ops = [op for op in norm.valid if op.asset_code == "USDT"]

        # Should have 2 USDT operations: transfer_out (from buy) and transfer_in (from sell)
        assert len(usdt_ops) == 2, \
            f"Expected 2 USDT operations, got {len(usdt_ops)}"

        # First should be transfer_out (from buy)
        op1 = next(op for op in usdt_ops if op.external_id.startswith("buy_eth"))
        assert op1.operation_type == "transfer_out", \
            f"REGRESSION FAILED: Buy should create transfer_out, got {op1.operation_type}"

        # Second should be transfer_in (from sell)
        op2 = next(op for op in usdt_ops if op.external_id.startswith("sell_eth"))
        assert op2.operation_type == "transfer_in", \
            f"REGRESSION FAILED: Sell should create transfer_in, got {op2.operation_type}"

        # Verify quantities are in correct direction
        assert op1.quantity > 0, "transfer_out should have positive quantity"
        assert op2.quantity > 0, "transfer_in should have positive quantity"
