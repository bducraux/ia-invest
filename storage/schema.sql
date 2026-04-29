-- IA-Invest SQLite Schema
-- Single database with logical separation by portfolio_id.
-- All monetary values are stored as INTEGER (cents in base currency) to avoid
-- floating-point rounding errors. Divide by 100 when displaying.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- members
-- Family members who own portfolios.  Every portfolio must have exactly one
-- owner.  Members cannot be hard-deleted while they still own active
-- portfolios — only inactivated.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS members (
    id              TEXT PRIMARY KEY,            -- kebab-case slug
    name            TEXT NOT NULL,
    display_name    TEXT,
    email           TEXT UNIQUE,                 -- nullable but unique when set
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);

-- ---------------------------------------------------------------------------
-- portfolios
-- Source of truth for portfolio configuration derived from portfolio.yml.
-- Each portfolio has a mandatory owner_id pointing at members.id.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolios (
    id              TEXT PRIMARY KEY,           -- matches portfolio.yml id
    name            TEXT NOT NULL,
    description     TEXT,
    base_currency   TEXT NOT NULL DEFAULT 'BRL',
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive', 'archived')),
    owner_id        TEXT NOT NULL REFERENCES members(id),
    config_json     TEXT,                       -- full portfolio.yml as JSON
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_portfolios_owner ON portfolios(owner_id);

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
    source          TEXT NOT NULL,              -- e.g. 'b3_csv', 'binance_csv'
    external_id     TEXT NOT NULL,              -- original ID from source file (SHA-256 fallback when absent)

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
    unit_price      INTEGER NOT NULL DEFAULT 0, -- cents (in BRL after fx conversion)
    gross_value     INTEGER NOT NULL DEFAULT 0, -- cents (in BRL after fx conversion)
    fees            INTEGER NOT NULL DEFAULT 0, -- cents (in BRL after fx conversion)
    net_value       INTEGER NOT NULL DEFAULT 0, -- cents (gross ± fees, in BRL)

    -- multi-currency: native (trade-currency) amounts and fx rate snapshot.
    -- For BRL trades: trade_currency='BRL', *_native == BRL columns,
    -- fx_rate_at_trade='1', fx_rate_source='native_brl'.
    trade_currency      TEXT NOT NULL DEFAULT 'BRL',
    unit_price_native   INTEGER NOT NULL DEFAULT 0,  -- cents in trade_currency
    gross_value_native  INTEGER NOT NULL DEFAULT 0,  -- cents in trade_currency
    fees_native         INTEGER NOT NULL DEFAULT 0,  -- cents in trade_currency
    fx_rate_at_trade    TEXT,                        -- Decimal as string
    fx_rate_source      TEXT,                        -- 'bacen_ptax', 'yahoo', ...

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
CREATE INDEX IF NOT EXISTS idx_operations_asset_type   ON operations(portfolio_id, asset_code, operation_type);
CREATE INDEX IF NOT EXISTS idx_operations_created_at   ON operations(created_at);

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
-- market_quotes_cache
-- Cached market quotes in cents for dashboard and position valuation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_quotes_cache (
    asset_code      TEXT PRIMARY KEY,
    price_cents     INTEGER NOT NULL,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_market_quotes_fetched_at ON market_quotes_cache(fetched_at);

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
-- fixed_income_positions
-- One row per individual brazilian fixed-income application (CDB, LCI, LCA).
-- Calculated values (gross/net/IR) are recomputed on the fly by the
-- FixedIncomeValuationService and are NOT persisted here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixed_income_positions (
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

CREATE INDEX IF NOT EXISTS idx_fi_positions_portfolio ON fixed_income_positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_fi_positions_status    ON fixed_income_positions(portfolio_id, status);
CREATE INDEX IF NOT EXISTS idx_fi_positions_asset     ON fixed_income_positions(portfolio_id, asset_type);
CREATE INDEX IF NOT EXISTS idx_fi_positions_maturity  ON fixed_income_positions(maturity_date);

-- ---------------------------------------------------------------------------
-- previdencia_snapshots
-- Latest statement snapshot for previdencia assets.
-- One row per portfolio + asset code, updated only when statement month is
-- not older than the current stored month.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS previdencia_snapshots (
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

    UNIQUE (portfolio_id, asset_code)
);

CREATE INDEX IF NOT EXISTS idx_prev_positions_portfolio ON previdencia_snapshots(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_prev_positions_period    ON previdencia_snapshots(portfolio_id, period_month);

-- ---------------------------------------------------------------------------
-- app_settings
-- Global application settings stored in SQLite.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ---------------------------------------------------------------------------
-- schema_migrations
-- Tracks applied migrations.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,               -- e.g. '0001'
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ---------------------------------------------------------------------------
-- daily_benchmark_rates
-- Historical daily benchmark rate cache (CDI, Selic, ...). Rates stored
-- as TEXT to preserve Decimal precision. Weekends and bank holidays are
-- simply absent from the table (the BACEN feed itself is the calendar).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_benchmark_rates (
    benchmark   TEXT NOT NULL,
    rate_date   TEXT NOT NULL,
    rate        TEXT NOT NULL,
    fetched_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (benchmark, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_benchmark_rates_lookup
    ON daily_benchmark_rates(benchmark, rate_date DESC);

-- ---------------------------------------------------------------------------
-- fx_rates
-- Historical FX rate cache for currency pair conversions (USDBRL, EURBRL, ...).
-- Rates stored as TEXT to preserve Decimal precision. One row per (pair, date).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fx_rates (
    pair        TEXT NOT NULL,
    rate_date   TEXT NOT NULL,
    rate        TEXT NOT NULL,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (pair, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_fx_rates_lookup
    ON fx_rates(pair, rate_date DESC);

-- ---------------------------------------------------------------------------
-- avenue_symbol_aliases
-- Persistent description→ticker cache for Avenue/Apex monthly PDF statements.
-- Apex statements identify equities by long descriptions in the BUY/SELL
-- section; the ticker symbol only appears in the PORTFOLIO SUMMARY. This
-- table learns from every imported statement so subsequent PDFs can resolve
-- the ticker even when the position is absent from that month's summary.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS avenue_symbol_aliases (
    portfolio_id    TEXT NOT NULL,
    asset_name      TEXT NOT NULL,
    asset_code      TEXT NOT NULL,
    cusip           TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (portfolio_id, asset_name)
);

CREATE INDEX IF NOT EXISTS idx_avenue_aliases_code
    ON avenue_symbol_aliases(portfolio_id, asset_code);

-- Record this baseline schema version
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0001', 'initial schema — all tables, indexes, and constraints');

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0002', 'add members table and portfolios.owner_id');
