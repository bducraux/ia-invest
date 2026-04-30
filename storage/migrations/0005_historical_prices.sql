-- 0005 — historical_prices cache
--
-- Persistent cache of monthly (and ad-hoc daily) closing prices used to
-- reconstruct historical portfolio value for the equity-curve report.
--
-- Once a closing price for a past date is known it is immutable, so this
-- cache has no TTL — entries are written once and reused indefinitely.
-- The current month's price still comes from `market_quotes_cache` (TTL).
--
-- Currency is stored to support international assets (USD, etc.); the
-- equity-curve service converts to BRL on the fly using `fx_rates`.

CREATE TABLE IF NOT EXISTS historical_prices (
    asset_code      TEXT NOT NULL,
    rate_date       TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    close_cents     INTEGER NOT NULL CHECK (close_cents >= 0),
    currency        TEXT NOT NULL DEFAULT 'BRL',
    source          TEXT NOT NULL,                  -- 'yahoo', 'brapi', 'manual', ...
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (asset_code, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_historical_prices_lookup
    ON historical_prices(asset_code, rate_date DESC);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0005', 'historical_prices cache for equity-curve reporting');
