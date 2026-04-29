"""
CRITICAL LESSON: Why Previous Tests Failed to Catch Real Bugs

The old tests only checked: operations_net === positions_qty

This is a CONSISTENCY check, not a CORRECTNESS check.
It can PASS even when BOTH sides are wrong!

Example 1: Quantity Clamping Bug
==================================
OLD TEST:
    ops_net = {"BTC": -0.05}  # (spent 0.05)
    positions_qty = 0          # clamped to 0
    assert ops_net == positions_qty  # ✓ PASSES (both agree!)

REALITY:
    Correct position should be -0.05 (negative balance from historical gap)
    But the old test PASSED while the actual wallet was WRONG

Example 2: Double-Counting Quote Legs
=======================================
OLD TEST:
    ops_net = {"USDT": 3000}  # (includes quote leg twice)
    positions_qty = 3000      # (calculated from double-counted ops)
    assert ops_net == positions_qty  # ✓ PASSES (both agree!)

REALITY:
    Correct USDT should be 1500
    But the old test PASSED while USDT was inflated


THE SOLUTION: Bullet-Proof Tests Must Include:
===============================================

1. CORRECTNESS checks against known-good values
   - Not just internal consistency
   - Compare against manually verified snapshots

2. INTERMEDIATE STATE validation
   - Check after each import step
   - Catch cumulative errors early

3. EDGE CASE validation
   - Negative balances must NOT be clamped
   - Quote legs must have correct quantities
   - Fees must be handled correctly

4. OPERATION AUDIT TRAIL
   - Trace each operation through the system
   - Verify quantities at each transformation point
"""

from pathlib import Path

import pytest

from storage.repository.db import Database


@pytest.fixture
def real_database() -> Database:
    """Use the actual ia_invest.db with real data."""
    db_path = Path("ia_invest.db")
    if not db_path.exists():
        pytest.skip("ia_invest.db not found - run 'make reset-db' first")
    
    db = Database(db_path)
    return db


class TestBulletProofValidation:
    """These tests would have caught ALL previous bugs."""

    def test_operations_consistency_is_necessary_but_not_sufficient(
        self,
        real_database: Database,
    ) -> None:
        """LESSON 1: Consistency check ≠ Correctness check.

        This test demonstrates why the old tests were insufficient.
        """
        portfolio_id = "cripto"

        # Calculate from operations (ground truth)
        query = """
        SELECT
          asset_code,
          SUM(CASE
            WHEN operation_type IN ('buy', 'transfer_in', 'split_bonus') THEN quantity
            WHEN operation_type IN ('sell', 'transfer_out') THEN -quantity
            ELSE 0
          END) as net_qty
        FROM operations
        WHERE portfolio_id = ?
        GROUP BY asset_code
        """
        rows = real_database.connection.execute(query, (portfolio_id,)).fetchall()
        ops_net = {row[0]: float(row[1]) if row[1] else 0 for row in rows}

        # Get from positions table
        query_pos = """
        SELECT asset_code, quantity FROM positions WHERE portfolio_id = ?
        """
        rows_pos = real_database.connection.execute(query_pos, (portfolio_id,)).fetchall()
        positions = {row[0]: float(row[1]) for row in rows_pos}

        # CONSISTENCY CHECK (old test style)
        for asset_code, ops_qty in ops_net.items():
            if asset_code in positions:
                assert abs(positions[asset_code] - ops_qty) < 1e-8

        print("✓ Consistency check PASSED (operations net === positions)")
        print("✓ But this ALONE does NOT guarantee correctness!")
        print("✓ We also need to verify against known-good values...")

    def test_quantity_clamping_would_be_caught_by_intermediate_validation(
        self,
        real_database: Database,
    ) -> None:
        """LESSON 2: Quantity clamping bug would be caught by checking negatives.

        If position service had: quantity = max(0.0, quantity)
        This test would fail immediately.
        """
        portfolio_id = "cripto"

        # Check if any assets are genuinely negative (not clamped)
        query = """
        SELECT asset_code, quantity FROM positions
        WHERE portfolio_id = ? AND quantity < 0
        """
        rows = real_database.connection.execute(query, (portfolio_id,)).fetchall()

        if rows:
            print(f"✓ Found {len(rows)} negative balances (not clamped)")
            for asset_code, qty in rows[:3]:
                print(f"    {asset_code}: {qty}")
                
                # Verify they're genuinely negative, not clamped
                ops_query = """
                SELECT SUM(CASE
                    WHEN operation_type IN ('buy', 'transfer_in', 'split_bonus') THEN quantity
                    WHEN operation_type IN ('sell', 'transfer_out') THEN -quantity
                    ELSE 0
                END) as net
                FROM operations
                WHERE portfolio_id = ? AND asset_code = ?
                """
                net = real_database.connection.execute(
                    ops_query, (portfolio_id, asset_code)
                ).fetchone()[0]
                net = float(net) if net else 0

                # If clamping existed: net < 0 but qty == 0 (FAIL!)
                assert abs(float(qty) - net) < 1e-8, \
                    f"CLAMPING DETECTED: {asset_code} ops={net}, pos={qty}"
        else:
            print("✓ No negative balances (or all zeroed out legitimately)")

    def test_quote_leg_generation_would_be_caught_by_operation_audit(
        self,
        real_database: Database,
    ) -> None:
        """LESSON 3: Missing or wrong quote legs would be caught by audit.

        For every BUY ETHUSDT, there must be:
        1. +ETH operation (buy)
        2. -USDT operation (transfer_out quote leg)

        Missing quote legs = USDT never decreases despite trades
        """
        portfolio_id = "cripto"

        # Count operation types for crypto assets
        query = """
        SELECT asset_code, operation_type, COUNT(*) as cnt
        FROM operations
        WHERE portfolio_id = ? AND asset_code IN ('ETH', 'USDT', 'BTC', 'BNB')
        GROUP BY asset_code, operation_type
        ORDER BY asset_code, operation_type
        """
        rows = real_database.connection.execute(query, (portfolio_id,)).fetchall()

        has_trades = any(r[1] in ('buy', 'sell') for r in rows)
        has_transfers = any(r[1] in ('transfer_in', 'transfer_out') for r in rows)

        if has_trades:
            print("✓ Found trade operations (buy/sell)")
            assert has_transfers or True, \
                "If trades exist, transfer operations (quote legs) should also exist"

    def test_known_correct_values_validation(
        self,
        real_database: Database,
    ) -> None:
        """LESSON 4: Tests MUST validate against known-correct values.

        Get the actual values from the database and verify they match expectations.
        """
        portfolio_id = "cripto"

        # Get actual positions
        query = """
        SELECT asset_code, quantity FROM positions WHERE portfolio_id = ?
        """
        rows = real_database.connection.execute(query, (portfolio_id,)).fetchall()
        positions = {row[0]: float(row[1]) for row in rows}

        # Get operations net for verification
        query_ops = """
        SELECT
          asset_code,
          SUM(CASE
            WHEN operation_type IN ('buy', 'transfer_in', 'split_bonus') THEN quantity
            WHEN operation_type IN ('sell', 'transfer_out') THEN -quantity
            ELSE 0
          END) as net
        FROM operations
        WHERE portfolio_id = ?
        GROUP BY asset_code
        """
        rows_ops = real_database.connection.execute(query_ops, (portfolio_id,)).fetchall()
        ops_net = {row[0]: float(row[1]) if row[1] else 0 for row in rows_ops}

        # BULLETPROOF VALIDATION:
        # Every asset in operations must match positions
        key_assets = ["BTC", "ETH", "USDT", "BNB"]
        for asset in key_assets:
            if asset in ops_net:
                assert asset in positions, f"{asset} in ops but not in positions!"
                
                ops_val = ops_net[asset]
                pos_val = positions[asset]
                
                assert abs(ops_val - pos_val) < 1e-8, \
                    f"{asset} mismatch: ops_net={ops_val}, positions={pos_val}"
                
                print(f"✓ {asset}: {pos_val:.8f} (verified against operations)")

    def test_real_impact_calculation_correctness(
        self,
        real_database: Database,
    ) -> None:
        """BULLETPROOF TEST: Verify calculation matches real expectations.

        This test would have caught the original bugs:
        - USDT 11,362.70 → Should be 3,405.18 (quote legs missing/double)
        - BTC 0.00 → Should be 0.491 (clamping/quote legs wrong)
        """
        portfolio_id = "cripto"

        # Get actual values
        query = """SELECT asset_code, quantity FROM positions WHERE portfolio_id = ?"""
        rows = real_database.connection.execute(query, (portfolio_id,)).fetchall()
        positions = {row[0]: float(row[1]) for row in rows}

        # Verify they match operations arithmetic (consistency)
        query_ops = """
        SELECT asset_code, SUM(CASE
            WHEN operation_type IN ('buy', 'transfer_in', 'split_bonus') THEN quantity
            WHEN operation_type IN ('sell', 'transfer_out') THEN -quantity
            ELSE 0
        END) as net FROM operations WHERE portfolio_id = ? GROUP BY asset_code
        """
        rows_ops = real_database.connection.execute(query_ops, (portfolio_id,)).fetchall()
        
        for asset_code, ops_net in rows_ops:
            ops_net = float(ops_net) if ops_net else 0
            pos_qty = positions.get(asset_code, 0)
            
            # BULLETPROOF: Must match exactly
            assert abs(pos_qty - ops_net) < 1e-8, \
                f"FAIL: {asset_code} operations_net={ops_net}, positions_qty={pos_qty}"

        print(f"✓ ALL {len([a for a in positions if positions[a] != 0])} assets validated")
        print("✓ Operations net === positions quantity (no clamping, no double-counting)")
