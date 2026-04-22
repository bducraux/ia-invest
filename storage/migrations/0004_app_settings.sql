-- 0004_app_settings.sql
-- Global application settings persisted in SQLite.

CREATE TABLE IF NOT EXISTS app_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0004', 'application settings table');
