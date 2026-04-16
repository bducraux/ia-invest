-- Migration 0001: initial schema
-- This migration is recorded automatically when schema.sql is applied for the first time.
-- See storage/schema.sql for the full baseline schema.

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0001', 'initial schema');
