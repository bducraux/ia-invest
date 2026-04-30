-- 0004 — previdencia snapshots: keep history per period_month
--
-- Replaces the UNIQUE (portfolio_id, asset_code) constraint with
-- UNIQUE (portfolio_id, asset_code, period_month) so that re-importing
-- past statements accumulates history instead of overwriting the latest
-- snapshot. This unlocks monthly equity-curve reporting for previdencia.
--
-- SQLite does not support DROP CONSTRAINT, so we recreate the table.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

CREATE TABLE previdencia_snapshots__new (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id                  TEXT NOT NULL REFERENCES portfolios(id),
    import_job_id                 INTEGER REFERENCES import_jobs(id),

    asset_code                    TEXT NOT NULL,
    product_name                  TEXT NOT NULL,
    quantity                      REAL NOT NULL CHECK (quantity >= 0),
    unit_price_cents              INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    market_value_cents            INTEGER NOT NULL CHECK (market_value_cents >= 0),
    period_month                  TEXT NOT NULL,
    period_start_date             TEXT,
    period_end_date               TEXT,
    source_file                   TEXT,

    created_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    UNIQUE (portfolio_id, asset_code, period_month)
);

INSERT INTO previdencia_snapshots__new (
    id, portfolio_id, import_job_id, asset_code, product_name,
    quantity, unit_price_cents, market_value_cents,
    period_month, period_start_date, period_end_date,
    source_file, created_at, updated_at
)
SELECT
    id, portfolio_id, import_job_id, asset_code, product_name,
    quantity, unit_price_cents, market_value_cents,
    period_month, period_start_date, period_end_date,
    source_file, created_at, updated_at
FROM previdencia_snapshots;

DROP TABLE previdencia_snapshots;
ALTER TABLE previdencia_snapshots__new RENAME TO previdencia_snapshots;

CREATE INDEX IF NOT EXISTS idx_prev_positions_portfolio ON previdencia_snapshots(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_prev_positions_period    ON previdencia_snapshots(portfolio_id, period_month);
CREATE INDEX IF NOT EXISTS idx_prev_positions_asset_per ON previdencia_snapshots(portfolio_id, asset_code, period_month DESC);

COMMIT;

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0004', 'previdencia snapshots keep history per period_month');
