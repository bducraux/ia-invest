-- 0006 — asset_metadata
--
-- Cross-domain master registry per asset. Decouples CNPJ and the structural
-- classification (`asset_class`) from `operations`/`positions` so the same
-- ticker shared across multiple portfolios reuses the same record.
--
-- `asset_class` drives the section/code mapping in the IRPF report (when
-- applicable) and groups assets for sector / portfolio analytics:
--   - acao   → Bens 03▷01, Rend. Isentos 09 (dividendos), Trib. Excl. 10 (JCP),
--              Rend. Isentos 18 (bonificação)
--   - fii    → Bens 07▷03, Rend. Isentos 99
--   - fiagro → Bens 07▷02, Rend. Isentos 99
--   - bdr    → Bens 03▷08 (futuro)
--   - etf    → Bens 07▷09 (futuro)
--
-- V1 inicial: tudo com sufixo `11` é classificado como `fii`. Reclassificação
-- para `fiagro` é manual (ou via skill de IA), gravando aqui.

CREATE TABLE IF NOT EXISTS asset_metadata (
    asset_code          TEXT PRIMARY KEY,
    cnpj                TEXT,
    asset_class         TEXT NOT NULL
                            CHECK (asset_class IN ('acao','fii','fiagro','bdr','etf')),
    asset_name_oficial  TEXT,
    source              TEXT NOT NULL DEFAULT 'manual',
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_asset_metadata_class
    ON asset_metadata(asset_class);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0006', 'asset_metadata registry for IRPF classification (cnpj, asset_class)');
