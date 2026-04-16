-- IA-Invest SQLite Schema
-- Single database with logical separation by portfolio_id.
-- All monetary values are stored as INTEGER (cents in base currency) to avoid
-- floating-point rounding errors. Divide by 100 when displaying.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- portfolios
-- Source of truth for portfolio configuration derived from portfolio.yml.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolios (
    id              TEXT PRIMARY KEY,           -- matches portfolio.yml id
    name            TEXT NOT NULL,
    description     TEXT,
    base_currency   TEXT NOT NULL DEFAULT 'BRL',
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive', 'archived')),
    config_json     TEXT,                       -- full portfolio.yml as JSON
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ---------------------------------------------------------------------------
-- operations
-- Normalised investment operations (buy, sell, dividend, split, etc.).
-- One row per atomic event, linked to a portfolio.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id    TEXT NOT NULL REFERENCES portfolios(id),
    import_job_id   INTEGER REFERENCES import_jobs(id),

    -- identification / deduplication
    source          TEXT NOT NULL,              -- e.g. 'b3_pdf', 'binance_csv'
    external_id     TEXT,                       -- original ID from source file

    -- asset
    asset_code      TEXT NOT NULL,              -- ticker, ISIN, symbol
    asset_type      TEXT NOT NULL,              -- stock, fii, etf, bdr, bond, crypto, …
    asset_name      TEXT,

    -- operation
    operation_type  TEXT NOT NULL,              -- buy, sell, dividend, jcp, split, merge, …
    operation_date  TEXT NOT NULL,              -- ISO 8601 date (YYYY-MM-DD)
    settlement_date TEXT,                       -- ISO 8601 date

    -- financials (stored as integer cents)
    quantity        REAL NOT NULL DEFAULT 0,    -- number of shares/units (can be fractional)
    unit_price      INTEGER NOT NULL DEFAULT 0, -- cents
    gross_value     INTEGER NOT NULL DEFAULT 0, -- cents
    fees            INTEGER NOT NULL DEFAULT 0, -- cents (brokerage, taxes, etc.)
    net_value       INTEGER NOT NULL DEFAULT 0, -- cents (gross ± fees)

    -- metadata
    broker          TEXT,
    account         TEXT,
    notes           TEXT,
    raw_data_json   TEXT,                       -- original raw record as JSON

    -- audit
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    -- deduplication constraint (configured per portfolio but enforced at DB level)
    UNIQUE (portfolio_id, source, external_id, operation_date, asset_code, operation_type)
);

CREATE INDEX IF NOT EXISTS idx_operations_portfolio    ON operations(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_operations_asset        ON operations(portfolio_id, asset_code);
CREATE INDEX IF NOT EXISTS idx_operations_date         ON operations(portfolio_id, operation_date);
CREATE INDEX IF NOT EXISTS idx_operations_type         ON operations(portfolio_id, operation_type);

-- ---------------------------------------------------------------------------
-- positions
-- Materialised / cached consolidated position per (portfolio, asset).
-- Recalculated after each import batch; not the source of truth (operations are).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id    TEXT NOT NULL REFERENCES portfolios(id),
    asset_code      TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    asset_name      TEXT,

    quantity        REAL NOT NULL DEFAULT 0,
    avg_price       INTEGER NOT NULL DEFAULT 0,     -- cents
    total_cost      INTEGER NOT NULL DEFAULT 0,     -- cents
    realized_pnl    INTEGER NOT NULL DEFAULT 0,     -- cents
    dividends       INTEGER NOT NULL DEFAULT 0,     -- cents received

    first_operation_date TEXT,
    last_operation_date  TEXT,
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    UNIQUE (portfolio_id, asset_code)
);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id);

-- ---------------------------------------------------------------------------
-- import_jobs
-- Audit trail for each file import attempt.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id    TEXT NOT NULL REFERENCES portfolios(id),
    source_type     TEXT NOT NULL,              -- extractor type used
    file_name       TEXT NOT NULL,
    file_hash       TEXT,                       -- SHA-256 of the original file
    file_path       TEXT,                       -- path at time of import (informational)

    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'done', 'partial', 'failed')),

    total_records   INTEGER DEFAULT 0,
    valid_records   INTEGER DEFAULT 0,
    skipped_records INTEGER DEFAULT 0,          -- deduplicated / already imported
    error_records   INTEGER DEFAULT 0,

    started_at      TEXT,
    finished_at     TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_import_jobs_portfolio ON import_jobs(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_import_jobs_status    ON import_jobs(status);

-- ---------------------------------------------------------------------------
-- import_errors
-- Individual parsing / validation errors per import job.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_job_id   INTEGER NOT NULL REFERENCES import_jobs(id),
    row_index       INTEGER,                    -- 0-based row in source file
    field           TEXT,                       -- field name if applicable
    error_type      TEXT NOT NULL,              -- 'parsing', 'validation', 'deduplication', …
    message         TEXT NOT NULL,
    raw_data_json   TEXT,                       -- raw row that caused the error
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_import_errors_job ON import_errors(import_job_id);

-- ---------------------------------------------------------------------------
-- schema_migrations
-- Tracks applied migrations.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,               -- e.g. '0001'
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Record this baseline migration
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0001', 'initial schema');
