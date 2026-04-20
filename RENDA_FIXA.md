# Renda Fixa — V1 (MVP)

Suporte inicial para aplicações bancárias brasileiras de renda fixa.
Cada aplicação é tratada como **um único registro independente** (sem
lotes, sem agrupamento fiscal, sem consolidação por contrato). O sistema
**recalcula** o valor bruto e líquido sempre na **data atual** da
aplicação (clock injetável).

## Escopo da V1

| Categoria          | Suportado na V1                          |
| ------------------ | ---------------------------------------- |
| Tipos de ativo     | `CDB`, `LCI`, `LCA`                      |
| Remunerações       | `PRE` (prefixado), `CDI_PERCENT`         |
| Benchmark          | `CDI` (para `CDI_PERCENT`)               |
| Investidor         | Pessoa Física (`PF`)                     |
| Moeda              | `BRL`                                    |

## Decisões e simplificações deliberadas do MVP

* **IOF é ignorado.** É uma simplificação de produto. A entidade
  `FixedIncomeTaxService.calculate_iof` retorna `Decimal(0)` e está
  pronta para ser substituída quando a IOF regressiva for implementada.
* **LCI/LCA PF** são tratadas como **isentas de IR**.
* **CDB PF** usa a tabela regressiva oficial:
  * 0..180 dias → 22,5%
  * 181..360 dias → 20%
  * 361..720 dias → 17,5%
  * > 720 dias → 15%
* **Prefixado** usa convenção de dias corridos com base 365:
  `factor = (1 + i_a)^(days/365)`. Banks frequentemente usam 252 dias
  úteis; deixamos a convenção isolada em
  `_PRE_DAYS_IN_YEAR` para troca futura sem refactor.
* **% do CDI** acumula apenas em **dias úteis**, multiplicativamente:
  `daily_factor = (1 + cdi_d) ^ (X/100)`.
* **Vencimento congela o valor.** Após `maturity_date`, o bruto é
  fixado no cálculo do dia do vencimento (status `MATURED`/`REDEEMED`
  permanecem a critério do operador no MVP).
* **Sem inferência por tipo.** Vencimento, liquidez e carência saem
  exclusivamente dos dados explícitos do registro/CSV.
* **Bruto não vem do banco.** Campos `imported_*` existem apenas para
  conferência opcional; o sistema nunca os usa para cálculo.
* **Arredondamento monetário:** toda a aritmética interna é em
  `Decimal` com precisão alta (40 dígitos no contexto local). O
  arredondamento para centavos acontece **uma única vez**, no momento
  de montar o resultado (`ROUND_HALF_EVEN`, banker's rounding). Valores
  ficam armazenados como inteiros em centavos, alinhados com o restante
  do projeto.

## Arquitetura

```
domain/
  fixed_income.py              # Entidade FixedIncomePosition + enums
  fixed_income_tax.py          # FixedIncomeTaxService (IR, hook IOF)
  fixed_income_rates.py        # DailyRateProvider + InMemory/Flat providers
  fixed_income_valuation.py    # FixedIncomeValuationService (puro)
normalizers/
  fixed_income_csv.py          # FixedIncomeCSVImporter
storage/
  schema.sql                   # tabela fixed_income_positions
  migrations/0003_fixed_income.sql
  repository/fixed_income.py   # FixedIncomePositionRepository
mcp_server/
  http_api.py                  # endpoints REST (list/detail/create/import)
frontend/src/app/(dashboard)/fixed-income/page.tsx   # UI mínima
```

### Provider de CDI (extensível)

`DailyRateProvider` é abstrato. A V1 envia:

* `InMemoryCDIRateProvider` — para testes e seeds.
* `FlatCDIRateProvider` — taxa diária constante para exemplos.

Adapters reais (BCB, brokers) devem subclassar `DailyRateProvider` e
ser ligados na camada de aplicação (no MVP a UI não calcula CDI por
padrão; chamar a API de cálculo retorna o valor bruto = principal e
`is_complete=False` com motivo claro). Isso evita regredir
silenciosamente para zero quando a série não está disponível.

## CSV de importação

Cabeçalho **snake_case**. Mínimo:

```
institution,asset_type,product_name,remuneration_type,application_date,maturity_date,principal_applied_brl
```

Opcionais: `benchmark`, `benchmark_percent`, `fixed_rate_annual_percent`,
`liquidity_label`, `imported_gross_value_brl`, `imported_net_value_brl`,
`imported_estimated_ir_brl`, `valuation_reference_date`, `notes`.

Validações principais:

* `asset_type ∈ {CDB, LCI, LCA}`
* `remuneration_type ∈ {PRE, CDI_PERCENT}`
* `PRE` → `fixed_rate_annual_percent` obrigatório
* `CDI_PERCENT` → `benchmark = CDI` e `benchmark_percent` obrigatório
* `principal_applied_brl > 0`, parseado como `Decimal` (aceita
  formatação brasileira: `"1.234,56"`)
* Datas inválidas são rejeitadas com mensagem clara

`investor_type` assume `PF` por padrão.

## Endpoints HTTP

| Método | Rota                                                         |
| ------ | ------------------------------------------------------------ |
| GET    | `/api/portfolios/{id}/fixed-income`                          |
| GET    | `/api/portfolios/{id}/fixed-income/{position_id}`            |
| POST   | `/api/portfolios/{id}/fixed-income`                          |
| POST   | `/api/portfolios/{id}/fixed-income/import-csv` (multipart)   |

A resposta sempre inclui `grossValueCurrentBrl`, `estimatedIrCurrentBrl`,
`netValueCurrentBrl`, `taxBracketCurrent`, `daysSinceApplication`,
`valuationDate`, `isComplete`/`incompleteReason`, e — quando o CSV
trouxe valores de conferência — `grossDiffBrl` / `netDiffBrl`.

## UI

Rota: `/fixed-income`.

Cada linha é uma aplicação. A página exibe explicitamente:

* "Valor bruto atual"
* "IR estimado no resgate hoje"
* "Valor líquido estimado hoje"

E os avisos do MVP:

* CDB → "valor líquido considera IR estimado com base na data atual"
* LCI/LCA → "ativo isento de IR para PF no modelo atual do app"
* Toda a V1 → "IOF não é considerado nesta versão"

## Testes

Cobertos em `tests/test_domain/test_fixed_income_tax.py`,
`tests/test_domain/test_fixed_income_valuation.py`,
`tests/test_normalizers/test_fixed_income_csv.py`,
`tests/test_storage/test_fixed_income_repository.py` e
`tests/test_api/test_fixed_income_api.py`:

* CDB prefixado em cada faixa de IR (22.5 / 20 / 17.5 / 15%)
* CDB %CDI com série fake
* LCI/LCA prefixados e %CDI sem IR
* Validação de campos obrigatórios do CSV
* Falha ao importar `PRE` sem `fixed_rate_annual_percent`
* Falha ao importar `CDI_PERCENT` sem `benchmark_percent`
* Cálculo usando relógio injetado (`FixedClock`)
* Arredondamento monetário consistente (sem uso de `float` binário)
* Comparação entre valor calculado e valor importado, quando existir

## Próximos passos (deixados em aberto, sem código)

* IOF regressivo (substituir o stub em `FixedIncomeTaxService.calculate_iof`)
* IPCA+ e Selic como benchmarks adicionais
* Resgates parciais, amortizações, cupons
* Importadores específicos por instituição (Nubank, Inter, BB, ...)
* Adapter real para a série CDI/Selic (BCB SGS), com cache local
