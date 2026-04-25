-- Add multi-currency support to operations.
--
-- Existing rows are 100% BRL: defaults preserve their semantics
-- (trade_currency='BRL', native = BRL fields, fx_rate_at_trade='1').
-- For new rows in foreign currencies, the *_native columns store the value
-- in the trading currency cents, and the existing BRL columns store the
-- converted value at fx_rate_at_trade.

ALTER TABLE operations
    ADD COLUMN trade_currency TEXT NOT NULL DEFAULT 'BRL';

ALTER TABLE operations
    ADD COLUMN unit_price_native INTEGER NOT NULL DEFAULT 0;

ALTER TABLE operations
    ADD COLUMN gross_value_native INTEGER NOT NULL DEFAULT 0;

ALTER TABLE operations
    ADD COLUMN fees_native INTEGER NOT NULL DEFAULT 0;

ALTER TABLE operations
    ADD COLUMN fx_rate_at_trade TEXT;

ALTER TABLE operations
    ADD COLUMN fx_rate_source TEXT;

-- Backfill native fields for legacy BRL rows so reporting stays consistent.
UPDATE operations
   SET unit_price_native  = unit_price,
       gross_value_native = gross_value,
       fees_native        = fees,
       fx_rate_at_trade   = '1',
       fx_rate_source     = 'native_brl'
 WHERE trade_currency = 'BRL'
   AND unit_price_native = 0
   AND gross_value_native = 0;

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0007', 'multi-currency support on operations (trade_currency + native amounts + fx_rate)');
