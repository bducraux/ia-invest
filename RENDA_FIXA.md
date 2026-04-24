# Renda Fixa

Este documento descreve como a renda fixa funciona hoje no IA-Invest.

Cada aplicação é tratada como um registro independente (sem agrupamento por contrato, sem lote fiscal). O sistema armazena dados contratuais e recalcula valor bruto, IR estimado e valor líquido na data de consulta.

## Escopo Atual

| Categoria | Suportado |
| --- | --- |
| Tipos de ativo | `CDB`, `LCI`, `LCA` |
| Remunerações | `PRE`, `CDI_PERCENT` |
| Benchmark | `NONE` (PRE) e `CDI` (CDI_PERCENT) |
| Investidor | `PF` |
| Moeda | `BRL` |

## Modelo de Dados

Tabela principal: `fixed_income_positions`.

Campos de lifecycle atualmente usados:

- `status` com valores permitidos `ACTIVE` e `MATURED`
- `auto_reapply_enabled` (boolean)

Não há colunas de histórico de reinvestimento na posição. As ações de ciclo de vida removem a linha antiga quando aplicável.

## Regras de Valuation

- Cálculo monetário com `Decimal`; arredondamento para centavos apenas no resultado final (`ROUND_HALF_EVEN`).
- `CDB` para PF usa tabela regressiva de IR:
  - 0..180 dias: 22,5%
  - 181..360 dias: 20%
  - 361..720 dias: 17,5%
  - acima de 720 dias: 15%
- `LCI` e `LCA` para PF são isentas de IR.
- IOF ainda nao é aplicado (stub em `FixedIncomeTaxService`).
- Pós-vencimento: o valor é congelado na data de vencimento para fins de valuation.

### Fonte da Taxa CDI (BACEN)

Para remuneração `CDI_PERCENT`, o sistema usa a série diária histórica do CDI publicada pelo BACEN (SGS série 12), armazenada localmente em `daily_benchmark_rates`.

- Cada linha representa o CDI fracionário (ex.: `0.00043739`) em um dia útil B3. Finais de semana e feriados são naturalmente ausentes — a omissão pelo BACEN é a fonte de verdade do calendário B3 (sem dependência de pacote `holidays`).
- A valorização compõe o produto de `(1 + rate_d)` para cada dia útil entre `application_date+1` e `min(today, coverage_end)`. O `coverage_end` é a data mais recente disponível no cache; como o BACEN só publica o CDI do dia D em D+1, capear em `coverage_end` reproduz o que os apps de banco mostram.
- Dias úteis sem registro **dentro** do intervalo coberto são tratados como feriados (skip silencioso). Dias úteis sem registro **após** `coverage_end` marcariam a posição como `isComplete = false` — situação que, na prática, só ocorre se o sync estiver muito atrasado.
- Sem fallback manual: se `daily_benchmark_rates` estiver vazio, o backend tenta um sync BACEN imediatamente. Se a API estiver indisponível, posições `CDI_PERCENT` ficam com `isComplete = false` até o próximo sync bem-sucedido.

### Sincronização do CDI

Fonte: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados`. Sem dependências externas (usa `urllib`).

- CLI: `make sync-cdi` (incremental) ou `make sync-cdi-full` (refaz tudo desde 2018-01-01, ~2k linhas).
- API: `GET /api/benchmarks/CDI/coverage` e `POST /api/benchmarks/CDI/sync`.
- Auto-sync: ao servir requisições de fixed-income, o backend dispara um sync incremental best-effort se `coverage_end < today - 1` (controlável via env `IA_INVEST_BENCHMARK_AUTO_SYNC=0`). Falhas de rede nunca quebram a resposta.
- UI: card "Histórico CDI (BACEN)" em Settings, com cobertura, último fetch e botões de sync.

## Lifecycle de Aplicações

Comportamento operacional:

- Não existe fechamento automático da aplicação.
- Aplicações vencidas são sinalizadas na UI (`isMatured = true`) para chamar atenção do usuário.
- Ações manuais disponíveis:
  - `Fechar`: remove a posição (delete da linha).
  - `Reinvestir`: cria nova posição com principal igual ao valor líquido na data da ação e remove a posição antiga.

Auto reinvestir:

- Se `auto_reapply_enabled = true`, a reconciliação roda nas leituras da lista/detalhe.
- Para posições vencidas candidatas, o backend executa o mesmo fluxo de `Reinvestir` (cria nova + remove antiga).
- A operação é idempotente de forma natural porque a linha antiga deixa de existir.

## CSV de Importação

Formato esperado: cabeçalho em `snake_case`.

Exemplo de cabeçalho em uso:

```csv
institution,asset_type,product_name,remuneration_type,benchmark,benchmark_percent,liquidity_label,application_date,maturity_date,application_value
```

Colunas obrigatórias:

- `institution`
- `asset_type`
- `product_name`
- `remuneration_type`
- `application_date`
- `maturity_date`
- `application_value`

Colunas opcionais:

- `benchmark`
- `benchmark_percent`
- `fixed_rate_annual_percent`
- `liquidity_label`
- `notes`

Regras de validação:

- `asset_type` em `CDB`, `LCI`, `LCA`
- `remuneration_type` em `PRE`, `CDI_PERCENT`
- `PRE`: `fixed_rate_annual_percent` obrigatório e `benchmark = NONE` (ou vazio)
- `CDI_PERCENT`: `benchmark = CDI` e `benchmark_percent` obrigatório
- `application_value > 0`
- datas em `YYYY-MM-DD` ou `DD/MM/YYYY`
- parser monetário aceita formatos como `1234.56` e `1.234,56`

## API HTTP

Endpoints de renda fixa:

- `GET /api/portfolios/{portfolio_id}/fixed-income`
- `GET /api/portfolios/{portfolio_id}/fixed-income/{position_id}`
- `POST /api/portfolios/{portfolio_id}/fixed-income`
- `PATCH /api/portfolios/{portfolio_id}/fixed-income/{position_id}`
- `DELETE /api/portfolios/{portfolio_id}/fixed-income/{position_id}` (fechar)
- `POST /api/portfolios/{portfolio_id}/fixed-income/{position_id}/redeem` (reinvestir)
- `PATCH /api/portfolios/{portfolio_id}/fixed-income/{position_id}/auto-reapply` (auto reinvestir)
- `POST /api/portfolios/{portfolio_id}/fixed-income/import-csv`

Endpoints de benchmarks (suportam o valuation):

- `GET /api/benchmarks/{name}/coverage` → `{ benchmark, start, end, rowCount, lastFetchedAt }`
- `POST /api/benchmarks/{name}/sync` body opcional `{ startDate?, endDate?, fullRefresh? }` → `{ benchmark, rowsInserted, coverageStart, coverageEnd, source }`

Campos de resposta relevantes por posição:

- contratuais: `institution`, `assetType`, `productName`, `remunerationType`, `benchmark`, `applicationDate`, `maturityDate`, `principalAppliedBrl`
- valuation: `grossValueCurrentBrl`, `grossIncomeCurrentBrl`, `estimatedIrCurrentBrl`, `netValueCurrentBrl`, `taxBracketCurrent`, `valuationDate`, `daysSinceApplication`
- integridade: `isComplete`, `incompleteReason`
- lifecycle/ui: `status`, `autoReapplyEnabled`, `isMatured`

## Frontend

Tela: `frontend/src/app/(dashboard)/fixed-income/page.tsx`.

Comportamentos principais:

- lista consolidada por carteira (quando em escopo global)
- destaque visual para linha vencida
- badge `Vencido` para aplicações maduras
- ações por linha em menu: `Editar aplicação`, `Fechar posição`, `Reinvestir agora`
- `Reinvestir agora` aparece somente para aplicações vencidas sem auto reinvestir ativo
- configuração `Auto reinvestir` é feita no modal de edição

## Estrutura de Código

```text
domain/
  fixed_income.py
  fixed_income_rates.py             # FlatCDIRateProvider, InMemoryCDIRateProvider, SQLiteDailyRateProvider
  fixed_income_tax.py
  fixed_income_valuation.py
normalizers/
  fixed_income_csv.py
storage/
  schema.sql                         # inclui tabela daily_benchmark_rates
  migrations/0002_fixed_income_lifecycle.sql
  migrations/0003_drop_fi_lineage_columns.sql
  repository/fixed_income.py
  repository/benchmark_rates.py     # cache do CDI/Selic histórico
mcp_server/
  services/fixed_income_lifecycle.py
  services/benchmark_sync.py        # cliente BACEN SGS
  http_api.py
scripts/
  sync_benchmark_rates.py           # CLI: make sync-cdi / sync-cdi-full
frontend/src/app/(dashboard)/fixed-income/page.tsx
frontend/src/app/(dashboard)/settings/page.tsx   # card de cobertura do CDI
```

## Testes

Cobertura principal em:

- `tests/test_domain/test_fixed_income_tax.py`
- `tests/test_domain/test_fixed_income_valuation.py`
- `tests/test_domain/test_fixed_income_valuation_holiday_contract.py`
- `tests/test_domain/test_fixed_income_rates_sqlite_provider.py`
- `tests/test_domain/test_fixed_income_cdi_real_series_regression.py`  # bate contra fixture real do BACEN
- `tests/test_normalizers/test_fixed_income_csv.py`
- `tests/test_storage/test_fixed_income_repository.py`
- `tests/test_storage/test_benchmark_rates_repo.py`
- `tests/test_services/test_benchmark_sync.py`
- `tests/test_domain/test_fixed_income_lifecycle.py`
- `tests/test_api/test_fixed_income_api.py`

Casos cobertos incluem:

- faixas de IR do CDB
- cálculo PRE e CDI_PERCENT
- série diária via `SQLiteDailyRateProvider` com cap em `coverage_end`
- contrato de feriados: ausência dentro da cobertura ≠ gap (silent skip); ausência após `coverage_end` cabe accrual
- regressão de correção: posição vs. valor auditado calculado a partir de série BACEN real (Q1 2024)
- validação de CSV e parsing monetário
- lifecycle de fechar e reinvestir
- auto reinvestir idempotente
- contratos de API (incluindo delete e endpoint de reinvestir `/redeem`)
- sync BACEN: parse percent→fração, delta incremental, full refresh, erros de rede
