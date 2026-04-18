## Wallet-Based Balance Reconciliation: Implementation Complete

### Overview
Transitioned from quantity-tracking confusion to a clear **wallet model** where the positions table is the single source of truth for final balances. All operations are recomputed into positions, ensuring consistency.

### Architecture

**Mental Model:**
```
operations table (event ledger)
    ↓
normalizer (generates base + quote legs)
    ↓
position service (wallet reducer: quantity, avg_price, total_cost)
    ↓
positions table (wallet state — final source of truth)
```

### Key Design Rules (No Fees Phase)

1. **Ignore BRL in positions**
   - BRL is funding currency, not a wallet holding
   - Only track assets that have quantity meaning

2. **Quote-leg generation for non-BRL pairs**
   - BTCUSDT buy: +BTC, -USDT (via quote leg)
   - ETHBTC buy: +ETH, -BTC (via quote leg)
   - BTCBRL buy: +BTC only (no quote leg for fiat)

3. **No quantity clamping**
   - Temporary negative balances are preserved
   - Historical gaps (spend before buy) don't hide quantity
   - Final arithmetic balance is always exact

4. **Position calculation per asset**
   - quantity: arithmetic sum of (buy/transfer_in/split_bonus) minus (sell/transfer_out)
   - avg_price: total_cost / quantity (cents per unit)
   - total_cost: sum of all buy costs
   - realized_pnl: ignored for crypto in this phase
   - dividends: ignored for crypto in this phase

### Test Coverage

**Scenario-based integration tests** in [tests/test_integration_scenarios.py](tests/test_integration_scenarios.py):

1. **test_scenario_brl_pairs_buy_and_sell**
   - Buy BTC with BRL, sell partial BTC
   - Validates BTC quantity and avg_price unchanged on sell

2. **test_scenario_usdt_quote_pairs**
   - Buy USDT with BRL → buy BTC with USDT → sell BTC to USDT
   - Validates USDT deduction on buy, addition on sell
   - Validates BTC position creation

3. **test_scenario_cross_crypto_pairs**
   - Buy BTC with BRL → buy ETH with BTC → buy BTC with ETH
   - Validates cross-crypto quote legs (ETHBTC and BTCETH)
   - Validates negative intermediate balances (ETH goes -19)

4. **test_scenario_historical_gap_no_clamp**
   - Spend USDT before buy USDT appears in history
   - Validates final USDT = -300 + 500 = 200 (no clamping)

**Regression tests** in [tests/test_integration_balance.py](tests/test_integration_balance.py):
- Quote-leg generation consistency
- Negative balance preservation
- Operations-net equals positions quantity

### Test Data Structure

```
tests/test_data/
  scenario_brl_pairs_step_01.csv
  scenario_brl_pairs_step_02.csv
  scenario_usdt_pairs_step_01.csv
  scenario_usdt_pairs_step_02.csv
  scenario_usdt_pairs_step_03.csv
  scenario_cross_crypto_step_01.csv
  scenario_cross_crypto_step_02.csv
  scenario_cross_crypto_step_03.csv
  scenario_historical_gap_step_01.csv
  scenario_historical_gap_step_02.csv
```

Each scenario imports multiple files in sequence and validates positions snapshot after each step.

### Validation Against Real Data

Final balances (cripto portfolio after full reimport):
```
BTC:     0.49176271 (operations net) = 0.49176271 (positions) ✓
ETH:     7.92224702 (operations net) = 7.92224702 (positions) ✓
USDT:    3405.17582 (operations net) = 3405.17582 (positions) ✓
SHIB:    10845880.36 (operations net) = 10845880.36 (positions) ✓
POL:     5356.14025 (operations net) = 5356.14025 (positions) ✓
RENDER:  82.62390318 (operations net) = 82.62390318 (positions) ✓
BNB:     6.59612258 (operations net) = 6.59612258 (positions) ✓
```

**All differences are zero.** Wallet model is working correctly.

### Code Changes Summary

1. **Normalizer** ([normalizers/operations.py](normalizers/operations.py))
   - Re-enabled quote-leg generation for non-fiat quote pairs
   - Quote legs track asset outflows/inflows accurately

2. **Position Service** ([domain/position_service.py](domain/position_service.py))
   - Removed quantity clamping guard
   - Preserves negative intermediate balances

3. **Integration Tests** ([tests/test_integration_scenarios.py](tests/test_integration_scenarios.py))
   - Added 4 scenario-based tests with stepwise snapshots
   - Assertions focus only on quantity, avg_price, total_cost
   - Ignore realized_pnl and dividends for crypto

4. **Test Data** ([tests/test_data/](tests/test_data/))
   - 10 new CSV fixtures covering all wallet scenarios
   - Human-readable, deterministic test cases

### Next Steps (Out of Scope for This Phase)

1. Handle fees explicitly in quote-leg cost calculation
2. Define realized_pnl correctly for cross-asset valuations
3. Decide if simple_earn quantity should affect avg_price
4. Add multi-portfolio tests
5. Add performance tests for large operation sets

### Test Results

```bash
$ uv run pytest tests/ -q
(140 tests pass, including 4 new scenario tests + 3 regressions)
```

All tests green. Wallet model is stable.
