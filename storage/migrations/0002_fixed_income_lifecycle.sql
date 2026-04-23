-- Add auto_reapply_enabled flag to fixed_income_positions.
ALTER TABLE fixed_income_positions
    ADD COLUMN auto_reapply_enabled INTEGER NOT NULL DEFAULT 0
        CHECK (auto_reapply_enabled IN (0, 1));

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0002', 'fixed-income auto_reapply_enabled flag');
