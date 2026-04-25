-- Historical FX rate cache for currency pair conversions (USDBRL, EURBRL, ...).
-- Rates stored as TEXT to preserve Decimal precision (same strategy as
-- daily_benchmark_rates). One row per (pair, rate_date).

CREATE TABLE IF NOT EXISTS fx_rates (
    pair        TEXT NOT NULL,                  -- e.g. 'USDBRL'
    rate_date   TEXT NOT NULL,                  -- ISO 8601 (YYYY-MM-DD)
    rate        TEXT NOT NULL,                  -- Decimal as string
    source      TEXT NOT NULL,                  -- 'bacen_ptax', 'yahoo', 'manual'
    fetched_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (pair, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_fx_rates_lookup
    ON fx_rates(pair, rate_date DESC);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0008', 'fx_rates cache (PTAX/Yahoo historical currency pair rates)');
