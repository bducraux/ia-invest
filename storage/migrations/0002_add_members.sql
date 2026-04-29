-- 0002 — add members and portfolios.owner_id
--
-- Introduces the Member entity (family member who owns one or more portfolios).
-- Every portfolio must have exactly one owner.  Members cannot be hard-deleted
-- if they still own active portfolios — only inactivated.
--
-- This migration assumes the database is being reset (no historical backfill).
-- Existing rows in `portfolios` would violate the NOT NULL constraint; callers
-- are expected to drop and re-create the database (`make reset-db`).

PRAGMA foreign_keys = ON;

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

-- portfolios.owner_id
-- Adding a NOT NULL column without a default to an existing table is unsafe in
-- SQLite; this migration is meant to run on a fresh database (or after the
-- previous portfolios table has been dropped via `make reset-db`).  When
-- applied on top of an existing schema with no portfolios, the ALTER below
-- succeeds.  When applied after rows already exist, the database must be
-- reset.
ALTER TABLE portfolios ADD COLUMN owner_id TEXT REFERENCES members(id);

CREATE INDEX IF NOT EXISTS idx_portfolios_owner ON portfolios(owner_id);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0002', 'add members table and portfolios.owner_id');
