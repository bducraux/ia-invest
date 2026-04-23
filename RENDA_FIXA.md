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

Não há colunas de histórico de resgate/reaplicação na posição. As ações de ciclo de vida removem a linha antiga quando aplicável.

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

## Lifecycle de Aplicações

Comportamento operacional:

- Não existe fechamento automático da aplicação.
- Aplicações vencidas são sinalizadas na UI (`isMatured = true`) para chamar atenção do usuário.
- Ações manuais disponíveis:
  - `Fechar`: remove a posição (delete da linha).
  - `Resgatar`: cria nova posição com principal igual ao valor líquido na data da ação e remove a posição antiga.

Auto reapply:

- Se `auto_reapply_enabled = true`, a reconciliação roda nas leituras da lista/detalhe.
- Para posições vencidas candidatas, o backend executa o mesmo fluxo de `Resgatar` (cria nova + remove antiga).
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
- `POST /api/portfolios/{portfolio_id}/fixed-income/{position_id}/redeem`
- `PATCH /api/portfolios/{portfolio_id}/fixed-income/{position_id}/auto-reapply`
- `POST /api/portfolios/{portfolio_id}/fixed-income/import-csv`

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
- ações por linha: `Editar`, `Fechar`, `Resgatar`, `Auto: on/off`
- `Resgatar` habilitado quando a aplicação está vencida

## Estrutura de Código

```text
domain/
  fixed_income.py
  fixed_income_rates.py
  fixed_income_tax.py
  fixed_income_valuation.py
normalizers/
  fixed_income_csv.py
storage/
  schema.sql
  migrations/0002_fixed_income_lifecycle.sql
  migrations/0003_drop_fi_lineage_columns.sql
  repository/fixed_income.py
mcp_server/
  services/fixed_income_lifecycle.py
  http_api.py
frontend/src/app/(dashboard)/fixed-income/page.tsx
```

## Testes

Cobertura principal em:

- `tests/test_domain/test_fixed_income_tax.py`
- `tests/test_domain/test_fixed_income_valuation.py`
- `tests/test_normalizers/test_fixed_income_csv.py`
- `tests/test_storage/test_fixed_income_repository.py`
- `tests/test_domain/test_fixed_income_lifecycle.py`
- `tests/test_api/test_fixed_income_api.py`

Casos cobertos incluem:

- faixas de IR do CDB
- cálculo PRE e CDI_PERCENT
- validação de CSV e parsing monetário
- lifecycle de fechar e resgatar
- auto reapply idempotente
- contratos de API (incluindo delete e redeem)
