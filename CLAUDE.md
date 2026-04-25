# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

IA-Invest is a **local-first Brazilian investment portfolio manager**. It ingests raw files (PDFs, CSVs, XLSX) from different brokers and exchanges, normalizes them into a single SQLite database, and exposes the consolidated data through two surfaces:

1. **MCP server** (`mcp_server/server.py`) — stdin/stdout protocol for Claude Desktop integration, allowing AI-driven portfolio analysis in natural language.
2. **FastAPI HTTP API** (`mcp_server/http_api.py`) — REST backend consumed by the Next.js frontend dashboard (`frontend/`).

Supported portfolio types: `renda-variavel` (stocks, FIIs, ETFs, BDRs), `renda-fixa` (CDB, LCI, LCA), `cripto` (crypto exchanges), `previdencia` (PGBL/VGBL pension), `internacional`.

---

## Commands

### Python backend

```bash
make install          # uv sync --extra dev
make init             # initialize SQLite database (ia_invest.db)
make reset-db         # drop DB, reinitialize, reimport all portfolios from processed/, sync CDI from BACEN
make import-all       # import all active portfolios from their inbox/ folders
make lint             # ruff check .
make type-check       # mypy .
make test             # uv run pytest -v

# Run a single test
uv run pytest tests/test_domain/test_fixed_income_valuation.py::test_name -v
```

### HTTP API (FastAPI — frontend backend)

```bash
make api-server                          # uvicorn on http://localhost:8010 with --reload
make api-server API_PORT=8020            # custom port
```

Env vars read at startup: `IA_INVEST_DB` (path to SQLite file, default `ia_invest.db`), `IA_INVEST_API_CORS_ORIGINS` (default `http://localhost:3000`), `IA_INVEST_QUOTES_ENABLED`, `IA_INVEST_QUOTES_TTL_SECONDS`, `IA_INVEST_QUOTES_TIMEOUT_SECONDS`, `IA_INVEST_BENCHMARK_AUTO_SYNC`.

### MCP server (for Claude Desktop)

```bash
make server   # uv run python -m mcp_server.server  (stdin/stdout)
```

### Portfolio management scripts

```bash
make create-portfolio                                        # interactive
uv run python scripts/import_portfolio.py --portfolio cripto
make check-balance ARGS="--portfolio cripto --assets BTC,ETH"
make adjust-balance ARGS="--portfolio cripto --asset BTC --real-quantity 0.55 --dry-run"
make portfolio-overview ARGS="--portfolio cripto --sort cost --hide-zero"
```

### Frontend (Next.js)

```bash
make frontend-install   # npm ci inside frontend/
make frontend-dev       # dev server at http://localhost:3000
make frontend-test      # Vitest unit tests
make frontend-lint      # ESLint
make frontend-build     # production build
```

For full local development both servers must be running: `make api-server` and `make frontend-dev`. The frontend reads `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8010`).

---

## Architecture

### Processing pipeline

```
portfolios/<id>/inbox/          ← raw files dropped here manually
        ↓ scripts/import_portfolio.py
        ↓ extractors/           ← parse file → list[dict] (no business logic)
        ↓ normalizers/          ← list[dict] → list[Operation] + quote-leg generation
        ↓ storage/repository/   ← persist to SQLite via repository pattern
        ↓ domain/               ← PositionService recomputes positions from operations
        ↓ portfolios/<id>/processed/ or rejected/
```

After import, files move from `inbox/` → `staging/` → `processed/` (or `rejected/` on failure). The file system is NOT the source of truth — the SQLite database is.

### SQLite schema (ia_invest.db)

Single database file with `portfolio_id` as the multi-tenancy key. All monetary values are **integers in cents** — never floats. Key tables:

| Table | Purpose |
|---|---|
| `portfolios` | Portfolio registry (mirrors portfolio.yml) |
| `operations` | Immutable event ledger — one row per atomic operation |
| `positions` | Materialised wallet state, recomputed after each import |
| `fixed_income_positions` | CDB/LCI/LCA records (gross/net recomputed on the fly, not stored) |
| `previdencia_snapshots` | Latest PGBL/VGBL statement snapshot per asset |
| `market_quotes_cache` | Cached market prices in cents with TTL |
| `import_jobs` / `import_errors` | Audit trail per file import |
| `app_settings` | Global settings: CDI, Selic, IPCA rates |
| `schema_migrations` | Migration version tracking |

Migrations are in `storage/migrations/` as `NNNN_description.sql`.

### Extractors (`extractors/`)

One extractor per file format/source. Each implements `BaseExtractor`:
- `can_handle(file_path) -> bool` — determine if this extractor applies
- `extract(file_path) -> list[dict]` — return raw records, no business logic

Existing extractors: `B3CsvExtractor`, `BrokerCsvExtractor`, `BinanceCsvExtractor`, `BinanceSimpleEarnExtractor`, `GorilaCsvExtractor`, `GorilaBXlsxExtractor`, `PrevidenciaIBMPDFExtractor`, `AvenueApexPdfExtractor`. Register new ones in `extractors/__init__.py`.

### Normalizers (`normalizers/`)

Convert `list[dict]` from extractors into `NormalizationResult(valid: list[Operation], errors: list[NormalizationError])`. All type conversions and date parsing happen here. Normalizers have no database access. The Binance normalizer (`normalizers/binance.py`) also generates **quote-legs** for non-BRL pairs (e.g., a BTCUSDT buy generates +BTC and −USDT as two separate operations).

### Domain (`domain/`)

Deterministic business rules — **never delegate these calculations to an AI agent**:

- `PositionService` — recomputes `quantity`, `avg_price` (weighted average cost), `total_cost`, `realized_pnl` from the full operations ledger. **No quantity clamping**: negative intermediate balances are preserved (historical data gaps create negative positions, not zeros).
- `DeduplicationService` — deduplication based on the unique constraint `(portfolio_id, source, external_id, operation_date, asset_code, operation_type)`.
- `FixedIncomeValuationService` — recomputes CDB/LCI/LCA gross value, IR, and net value on-the-fly using `DailyRateProvider` (injected). Uses `Decimal` internally; rounds to cents once at the end with `ROUND_HALF_EVEN`.
- `FixedIncomeTaxService` — CDB IR using the official 4-bracket regressive table; LCI/LCA are IR-exempt for PF. IOF is a stub returning zero in V1.

### MCP server (`mcp_server/`)

Two runtimes share the same repositories and domain logic:

- **`server.py`** — MCP protocol over stdin/stdout for Claude Desktop. Tools: `list_portfolios`, `get_portfolio_summary`, `get_portfolio_positions`, `get_portfolio_operations`, `compare_portfolios`, `get_consolidated_summary`.
- **`http_api.py`** — FastAPI REST API for the frontend. All Pydantic response models use **camelCase** field names. Key routes: `/api/portfolios`, `/api/portfolios/{id}/summary`, `/api/portfolios/{id}/positions`, `/api/portfolios/{id}/operations`, `/api/portfolios/{id}/fixed-income`, `/api/portfolios/{id}/previdencia`, `/api/quotes/refresh`, `/api/settings`.
- **`services/quotes.py`** — `MarketQuoteService` fetches live prices (brapi.dev/Yahoo Finance fallback) with a configurable TTL cache in `market_quotes_cache`.

The MCP and HTTP layers **never write raw SQL** — all queries go through `storage/repository/`.

### Frontend (`frontend/`)

Next.js App Router with TypeScript, Tailwind CSS v4, TanStack Query, Recharts.

- Route group `(dashboard)` shares a persistent sidebar layout. Pages: overview, positions, operations, dividends, fixed-income, previdencia, renda-variavel, cripto, portfolio detail, settings, import.
- All monetary values are **integers in cents** throughout the codebase. Money helpers in `@/lib/money`: `formatBRL(cents)`, `formatBRLSigned(cents)`, `formatPercent(ratio)`. The `Cents` branded type prevents accidental mixing of cents and reals.
- Dates over the wire are ISO `YYYY-MM-DD`. Display uses `formatDate` from `@/lib/date` in pt-BR format.
- API client: `@/lib/api.ts`. Query keys and TanStack Query hooks: `@/lib/queries.ts`.
- Dark mode is the default; toggled via `next-themes`.
- Some pages still import from `@/mocks/data` — new pages must use the real API via `@/lib/api.ts`.

### Wallet model (crypto / equities)

The `positions` table is the computed final state; `operations` is the immutable event ledger. The position reducer (`PositionService`) processes all operations in chronological order:
- `buy`, `transfer_in`, `split_bonus` → add to quantity
- `sell`, `transfer_out` → subtract from quantity
- Negative intermediate balances are **preserved** (no clamping to zero)
- BRL is a funding currency, never tracked as an asset position
- Non-BRL quote pairs generate a quote-leg: buying BTCUSDT adds `+BTC` and `−USDT`

### Fixed income (renda fixa) specifics

Each CSV row is an independent position (no lot grouping). Valuation is recomputed at request time from `principal_applied_brl`, `application_date`, `maturity_date`, and an injected `DailyRateProvider`. The `imported_*` columns (gross/net from the original CSV) are stored only for manual diff verification; they are never used in calculations. After maturity date, value is frozen at the maturity-day calculation.

---

## Testing approach

Tests must validate **correctness against known-good values**, not just internal consistency. A test that compares two code paths sharing the same bug will pass silently (see `TEST_STRATEGY.md` for the canonical example of quantity clamping that caused `0 == 0` to pass).

Four-layer pattern:
1. Consistency: `operations_net == positions_qty`
2. Correctness: compare to manually audited expected values
3. Edge cases: negative balances are preserved (not clamped)
4. Audit trail: quote-legs and operation types exist as expected

Key test files:
- `tests/test_integration_scenarios.py` — scenario-based wallet tests (BRL pairs, USDT pairs, cross-crypto, historical gaps)
- `tests/test_integration_balance.py` — regression: quote-leg consistency, negative balance preservation
- `tests/test_bulletproof_lessons.py` — correctness against real-data known-good values
- `tests/test_domain/` — unit tests for PositionService, FixedIncomeValuationService, FixedIncomeTaxService
- `tests/test_api/` — FastAPI endpoint integration tests

---

## Extending the system

**New extractor:**
1. Create `extractors/my_extractor.py` subclassing `BaseExtractor` with `can_handle()` and `extract()`.
2. Register in `extractors/__init__.py`.
3. Add tests in `tests/test_extractors/`.

**New MCP tool:**
1. Add function in `mcp_server/tools/`.
2. Register in `mcp_server/server.py`.

**New HTTP endpoint:**
Add to `mcp_server/http_api.py` reusing existing repositories — no direct SQL.

**New DB table or column:**
Add a migration file `storage/migrations/NNNN_description.sql` and register the version in the `INSERT OR IGNORE INTO schema_migrations` block of `storage/schema.sql`.

**New portfolio type:**
Create `templates/<new-type>/portfolio.yml`. The `create_portfolio.py` script discovers templates automatically.
