-- 0003 — namespace portfolios.id as owner__slug; add slug column
--
-- Background: previously `portfolios.id` was just the slugified portfolio
-- name (e.g. "renda-fixa").  Two members could not own portfolios sharing
-- the same slug because the second `upsert` overwrote the first via
-- `ON CONFLICT(id) DO UPDATE`.  This migration:
--
--   1. Adds a `slug` column carrying the raw, owner-local identifier.
--   2. Backfills slug from the existing id.
--   3. Renames each non-namespaced id to f"{owner_id}__{slug}" — also
--      cascading the change to every child table that stores
--      `portfolio_id` as a TEXT FK (SQLite does not auto-cascade these).
--   4. Adds a UNIQUE(owner_id, slug) index to prevent future collisions.
--
-- Foreign keys are temporarily disabled to allow the cross-table id rewrite
-- without tripping the FK enforcement on `operations.portfolio_id`,
-- `positions.portfolio_id`, etc.

PRAGMA foreign_keys = OFF;

ALTER TABLE portfolios ADD COLUMN slug TEXT;

UPDATE portfolios SET slug = id WHERE slug IS NULL;

-- Cascade id rewrite to every child table that stores portfolio_id as TEXT.
UPDATE operations
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = operations.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

UPDATE positions
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = positions.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

UPDATE import_jobs
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = import_jobs.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

UPDATE fixed_income_positions
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = fixed_income_positions.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

UPDATE previdencia_snapshots
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = previdencia_snapshots.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

UPDATE avenue_symbol_aliases
   SET portfolio_id = (
       SELECT owner_id || '__' || slug
         FROM portfolios
        WHERE portfolios.id = avenue_symbol_aliases.portfolio_id
   )
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE instr(id, '__') = 0);

-- Finally rewrite the parent table.
UPDATE portfolios
   SET id = owner_id || '__' || slug
 WHERE instr(id, '__') = 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_owner_slug
    ON portfolios(owner_id, slug);

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0003', 'namespace portfolios.id as owner__slug; add slug column');
