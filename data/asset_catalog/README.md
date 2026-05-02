# Catálogo de ativos (cross-domain)

Esta pasta é o **catálogo mestre versionado** do IA-Invest. Ela cobre todos
os ativos que o sistema precisa identificar/classificar, separados por
classe IRPF em um arquivo CSV cada. É consumido pelo `domain.asset_catalog`
loader e populado no banco via `make sync-asset-catalog`.

## Arquivos

| Arquivo | Classe IRPF (`asset_class`) | Origem típica |
|---|---|---|
| `acoes.csv`   | `acao`            | Edição manual + skill `asset-metadata-enrich` (B3, RI, CVM). |
| `fiis.csv`    | `fii` / `fiagro`  | Crawler [`scripts/crawler/fundsexplorer/generate_fiis_csv.py`](../../scripts/crawler/fundsexplorer/generate_fiis_csv.py). FIAGRO é reclassificado manualmente. |
| `criptos.csv` | `cripto`          | Edição manual. CNPJ fica vazio (não há registro CNPJ). |
| `stocks.csv`  | `stocks`          | Edição manual. Cobre ações/ETFs/REITs internacionais (US). CNPJ fica vazio. |

## Schema canônico

Todos os arquivos seguem o mesmo cabeçalho:

```
ticker,cnpj,razao_social,asset_class,sector_category,sector_subcategory,site_ri,fonte
```

- `ticker` — identificador único do ativo (uppercase). Não pode repetir entre arquivos.
- `cnpj` — formato `NN.NNN.NNN/NNNN-NN`. Opcional para `cripto` e `stocks`.
- `razao_social` — razão social oficial (não traduzir, não abreviar).
- `asset_class` — uma das classes acima. Tem que bater com o arquivo onde a linha mora.
- `sector_category` / `sector_subcategory` — taxonomia setorial. Para FIIs vem do
  campo `tipo` do FundsExplorer (`Tijolo: Lajes Corporativas` → `Tijolo` / `Lajes Corporativas`).
- `site_ri` — URL oficial da página de Relações com Investidores. Opcional, mas
  quando presente serve como atalho para a skill IA buscar dados sem gastar tokens
  varrendo a web.
- `fonte` — descrição curta da fonte primária (ex.: `B3 2026-04`, `FundsExplorer 2026-05`).

## Regras de edição

1. **Cada linha foi confirmada com pelo menos uma fonte oficial** (B3, RI, CVM, CNPJ.biz, etc.).
2. **Ticker renomeado** (ex.: `GALG11 → GARE11`) fica como duas linhas com o mesmo CNPJ —
   o ticker antigo preserva o histórico de operações.
3. **Manual prevalece**: nem o crawler nem o `sync_asset_catalog` sobrescrevem células
   já preenchidas. Edite à vontade neste CSV; rodar o crawler de novo não vai apagar
   sua reclassificação de `fii → fiagro`.
4. Linhas começando com `#` são comentários e ignoradas pelo loader.

## Fluxo de uso

```text
data/asset_catalog/*.csv  ←──────┐
       │                          │
       ▼                          │
domain.asset_catalog.load_catalog │ commits humanos / PRs
       │                          │
       ▼                          │
scripts/sync_asset_catalog.py ────┘
       │  (popula a tabela asset_metadata)
       ▼
storage/repository/asset_metadata.AssetMetadataRepository
       │
       ▼
mcp_server/http_api  ─►  /api/asset-metadata
domain/irpf/builder  ─►  Simulador IRPF
```

Para promover linhas preenchidas no banco (via skill IA ou via PATCH na UI) de
volta ao Git: `make dump-asset-metadata-seed ARGS=--write`.
