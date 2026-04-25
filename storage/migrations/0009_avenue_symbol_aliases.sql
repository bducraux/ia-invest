-- Persistent description→ticker cache for Avenue/Apex monthly statements.
--
-- Apex Clearing PDFs identify equities by long descriptions (e.g.
-- "ALPHABET INC CLASS A COMMON STOCK") in the BUY/SELL section, while the
-- ticker symbol (GOOGL) only appears in the PORTFOLIO SUMMARY of months
-- where the position is non-zero at the closing balance. To resolve names
-- on months where the summary is missing or has been liquidated, we keep
-- a per-portfolio alias cache that learns from every imported statement.
--
-- CUSIP is captured opportunistically (from the BUY/SELL section) but is
-- NOT used as the lookup key in V1.

CREATE TABLE IF NOT EXISTS avenue_symbol_aliases (
    portfolio_id    TEXT NOT NULL,
    asset_name      TEXT NOT NULL,   -- normalized: trim, upper, single spaces
    asset_code      TEXT NOT NULL,
    cusip           TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (portfolio_id, asset_name)
);

CREATE INDEX IF NOT EXISTS idx_avenue_aliases_code
    ON avenue_symbol_aliases(portfolio_id, asset_code);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0009', 'avenue_symbol_aliases (persistent description→ticker cache for Apex PDFs)');
