-- Drop lineage / redeem tracking columns from fixed_income_positions.
-- These were added in migration 0002 but are no longer needed: lifecycle
-- actions now delete the old row (close) or delete + create a fresh row
-- (redeem/reinvest). No history is retained in the database.

DROP INDEX IF EXISTS idx_fi_positions_source;

ALTER TABLE fixed_income_positions DROP COLUMN IF EXISTS source_position_id;
ALTER TABLE fixed_income_positions DROP COLUMN IF EXISTS redeemed_at;
ALTER TABLE fixed_income_positions DROP COLUMN IF EXISTS redeemed_net_value_brl;

-- Tighten the status CHECK to remove the now-unused REDEEMED value.
-- SQLite does not support ALTER TABLE ... MODIFY COLUMN so we recreate
-- the table via the standard rename-create-copy-drop sequence.
CREATE TABLE fixed_income_positions_new (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id                  TEXT NOT NULL REFERENCES portfolios(id),
    import_job_id                 INTEGER REFERENCES import_jobs(id),

    external_id                   TEXT,
    institution                   TEXT NOT NULL,
    asset_type                    TEXT NOT NULL CHECK (asset_type IN ('CDB','LCI','LCA')),
    product_name                  TEXT NOT NULL,
    remuneration_type             TEXT NOT NULL CHECK (remuneration_type IN ('PRE','CDI_PERCENT')),
    benchmark                     TEXT NOT NULL CHECK (benchmark IN ('NONE','CDI')),
    investor_type                 TEXT NOT NULL DEFAULT 'PF' CHECK (investor_type IN ('PF')),
    currency                      TEXT NOT NULL DEFAULT 'BRL',

    application_date              TEXT NOT NULL,
    maturity_date                 TEXT NOT NULL,
    liquidity_label               TEXT,
    principal_applied_brl         INTEGER NOT NULL CHECK (principal_applied_brl > 0),
    fixed_rate_annual_percent     REAL,
    benchmark_percent             REAL,
    notes                         TEXT,

    status                        TEXT NOT NULL DEFAULT 'ACTIVE'
                                       CHECK (status IN ('ACTIVE','MATURED')),
    auto_reapply_enabled          INTEGER NOT NULL DEFAULT 0
                                       CHECK (auto_reapply_enabled IN (0,1)),

    created_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO fixed_income_positions_new
    SELECT id, portfolio_id, import_job_id, external_id,
           institution, asset_type, product_name,
           remuneration_type, benchmark, investor_type, currency,
           application_date, maturity_date, liquidity_label,
           principal_applied_brl, fixed_rate_annual_percent, benchmark_percent,
           notes,
           CASE WHEN status IN ('ACTIVE','MATURED') THEN status ELSE 'ACTIVE' END,
           auto_reapply_enabled,
           created_at, updated_at
    FROM fixed_income_positions;

DROP TABLE fixed_income_positions;
ALTER TABLE fixed_income_positions_new RENAME TO fixed_income_positions;

CREATE INDEX IF NOT EXISTS idx_fi_positions_portfolio ON fixed_income_positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_fi_positions_status    ON fixed_income_positions(portfolio_id, status);
CREATE INDEX IF NOT EXISTS idx_fi_positions_asset     ON fixed_income_positions(portfolio_id, asset_type);
CREATE INDEX IF NOT EXISTS idx_fi_positions_maturity  ON fixed_income_positions(maturity_date);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0003', 'drop fixed-income lineage columns, tighten status CHECK');
