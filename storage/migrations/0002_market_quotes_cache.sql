-- 0002: add market quote cache table for API valuation endpoints

CREATE TABLE IF NOT EXISTS market_quotes_cache (
    asset_code      TEXT PRIMARY KEY,
    price_cents     INTEGER NOT NULL,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_market_quotes_fetched_at ON market_quotes_cache(fetched_at);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0002', 'market quote cache table');
