-- 0007 — asset_metadata cross-domain extension
--
-- Amplia o cadastro de ativos para fora do escopo IRPF: agora carrega também
-- categoria/subcategoria setorial, URL oficial de RI e metadados de
-- proveniência (data_source, last_synced_at). Inclui as classes `cripto` e
-- `stocks` (ações/ETFs/REITs internacionais), antes ausentes.
--
-- Observação sobre o CHECK: SQLite não suporta `ALTER TABLE ... ALTER COLUMN`,
-- então o CHECK original (apenas acao/fii/fiagro/bdr/etf) permanece em DBs
-- antigos. O fluxo recomendado para esta entrega é `make reset-db`, que
-- aplica o `schema.sql` atualizado de uma vez. Este arquivo registra a
-- versão e adiciona apenas as colunas novas (operação suportada pelo
-- ALTER TABLE).

ALTER TABLE asset_metadata ADD COLUMN sector_category TEXT;
ALTER TABLE asset_metadata ADD COLUMN sector_subcategory TEXT;
ALTER TABLE asset_metadata ADD COLUMN site_ri TEXT;
ALTER TABLE asset_metadata ADD COLUMN data_source TEXT;
ALTER TABLE asset_metadata ADD COLUMN last_synced_at TEXT;

CREATE INDEX IF NOT EXISTS idx_asset_metadata_sector
    ON asset_metadata(sector_category, sector_subcategory);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ('0007', 'asset_metadata cross-domain extension (sector, site_ri, data_source) and cripto/stocks classes');
