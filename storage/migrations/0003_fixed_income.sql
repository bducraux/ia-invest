-- 0003: fixed-income (renda fixa) positions table
--
-- One row per individual brazilian fixed-income application (CDB, LCI,
-- LCA in V1). All monetary values stored as INTEGER cents (BRL).
--
-- Calculated fields (gross/net/IR) are recomputed on the fly by
-- domain.fixed_income_valuation.FixedIncomeValuationService against the
-- application clock; they are not persisted here.

CREATE TABLE IF NOT EXISTS fixed_income_positions (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id                  TEXT NOT NULL REFERENCES portfolios(id),
    import_job_id                 INTEGER REFERENCES import_jobs(id),

    -- identification / classification
    external_id                   TEXT,
    institution                   TEXT NOT NULL,
    asset_type                    TEXT NOT NULL CHECK (asset_type IN ('CDB','LCI','LCA')),
    product_name                  TEXT NOT NULL,
    remuneration_type             TEXT NOT NULL CHECK (remuneration_type IN ('PRE','CDI_PERCENT')),
    benchmark                     TEXT NOT NULL CHECK (benchmark IN ('NONE','CDI')),
    investor_type                 TEXT NOT NULL DEFAULT 'PF' CHECK (investor_type IN ('PF')),
    currency                      TEXT NOT NULL DEFAULT 'BRL',

    -- contract
    application_date              TEXT NOT NULL,
    maturity_date                 TEXT NOT NULL,
    liquidity_label               TEXT,
    principal_applied_brl         INTEGER NOT NULL CHECK (principal_applied_brl > 0),
    fixed_rate_annual_percent     REAL,
    benchmark_percent             REAL,

    -- optional importer / conference fields
    imported_gross_value_brl      INTEGER,
    imported_net_value_brl        INTEGER,
    imported_estimated_ir_brl     INTEGER,
    valuation_reference_date      TEXT,
    notes                         TEXT,

    -- lifecycle
    status                        TEXT NOT NULL DEFAULT 'ACTIVE'
                                       CHECK (status IN ('ACTIVE','MATURED','REDEEMED')),

    -- audit
    created_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fi_positions_portfolio ON fixed_income_positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_fi_positions_status    ON fixed_income_positions(portfolio_id, status);
CREATE INDEX IF NOT EXISTS idx_fi_positions_asset     ON fixed_income_positions(portfolio_id, asset_type);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0003', 'fixed income positions table');
