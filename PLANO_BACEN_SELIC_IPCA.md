# Plano de Evolucao: SELIC e IPCA Historicos via BACEN

## Objetivo
Preparar a proxima evolucao do motor de renda fixa para suportar, alem de CDI, taxas historicas de:

- SELIC diaria (BACEN SGS serie 11)
- IPCA mensal (BACEN SGS serie 433)

Este documento descreve o plano completo de desenho, implementacao, testes, rollout e operacao.

## Contexto Atual
O projeto ja possui:

- Cache historico diario em SQLite na tabela `daily_benchmark_rates`
- Sync BACEN para CDI (SGS 12)
- Provider `SQLiteDailyRateProvider`
- Valuation CDI_PERCENT baseado em serie historica e `coverage_end`
- Endpoints de benchmark para coverage/sync
- Fluxo de `make reset-db` com bootstrap CDI

## Escopo da Evolucao

### Em escopo
- Adicionar sync historico de SELIC diario na mesma infraestrutura de benchmarks diarios
- Introduzir infraestrutura de series mensais para IPCA
- Definir contrato de valuation para papeis indexados a IPCA
- Expor status/cobertura de SELIC e IPCA na API e Settings
- Cobertura de testes unitarios, integracao e regressao

### Fora de escopo (nesta fase)
- Reprocessamento automatico de toda base historica em background
- Scheduler permanente (cron interno)
- Produtos de renda fixa com regras exoticas nao modeladas no dominio atual

## Premissas e Fontes

### BACEN (SGS)
- CDI diario: serie 12
- SELIC diaria: serie 11
- IPCA mensal: serie 433

### Premissas tecnicas
- Valores monetarios permanecem em centavos
- Calculo financeiro continua com `Decimal`
- Sem dependencia externa adicional para calendario
- Feriados/dias nao uteis: inferidos pela propria omissao da fonte diaria BACEN

## Arquitetura Alvo

### 1) Benchmarks diarios (CDI + SELIC)
Reutilizar a tabela existente `daily_benchmark_rates` com `benchmark` como chave logica.

- `benchmark = 'CDI'` -> SGS 12
- `benchmark = 'SELIC'` -> SGS 11

Sem mudanca estrutural obrigatoria no schema diario.

### 2) Benchmarks mensais (IPCA)
Criar nova tabela para evitar distorcoes de semantica diaria:

- Tabela proposta: `monthly_benchmark_rates`
- Colunas sugeridas:
  - `benchmark TEXT NOT NULL` (ex.: `IPCA`)
  - `reference_month TEXT NOT NULL` (`YYYY-MM`)
  - `rate TEXT NOT NULL` (percentual convertido para fracao conforme contrato)
  - `published_at TEXT NOT NULL`
  - `fetched_at TEXT NOT NULL`
  - PK (`benchmark`, `reference_month`)

Motivo: IPCA e mensal, com publicacao e uso por competencia, diferente de serie diaria.

## Mudancas de Dominio

### 1) Taxonomia de benchmark
Padronizar enum/logica para:

- `CDI` (daily)
- `SELIC` (daily)
- `IPCA` (monthly)

### 2) Providers
- Manter `SQLiteDailyRateProvider` para `CDI` e `SELIC`
- Adicionar `SQLiteMonthlyRateProvider` para `IPCA`
  - `get_monthly_rates(start_month, end_month, benchmark='IPCA')`
  - `get_coverage_end_month(benchmark='IPCA')`

### 3) Valuation
Definir comportamento por tipo de remuneracao:

- `CDI_PERCENT`: manter regra atual
- `SELIC_PERCENT` (novo tipo, se aprovado): composto por serie SELIC diaria
- `IPCA_PLUS_PRE` (novo tipo, se aprovado): composicao de inflacao mensal + spread

Observacao: antes de codar, decidir nomenclatura de remuneracao para evitar migracao semantica futura.

## Contrato Financeiro Proposto para IPCA
Antes da implementacao, fechar regra com exemplos auditaveis.

### Decisoes obrigatorias
1. Base temporal: mes cheio, pro-rata diario, ou data de aniversario
2. Defasagem de publicacao: usar ultimo IPCA publicado ou mes de competencia
3. Composicao com spread:
   - Multiplicativa: `(1+ipca)*(1+spread)`
   - Aditiva aproximada: `ipca + spread`
4. Arredondamento: manter `ROUND_HALF_EVEN` apenas no fim

Sem estas decisoes, nao iniciar codigo de valuation IPCA.

## API e Contratos

### Endpoints existentes a evoluir
- `GET /api/benchmarks/{name}/coverage`
- `POST /api/benchmarks/{name}/sync`

### Ajustes previstos
- Suportar `SELIC` e `IPCA` no mesmo endpoint
- Coverage para IPCA deve retornar meses (ou string clara de mes)
- Mensagens de erro explicitas para benchmark nao suportado

## Frontend (Settings)

### Estado desejado
Area "Historico BACEN" com cards por benchmark:

- CDI: cobertura diaria, ultima atualizacao, sync
- SELIC: cobertura diaria, ultima atualizacao, sync
- IPCA: cobertura mensal, ultima atualizacao, sync

### UX
- Botao sync incremental por benchmark
- Botao full refresh por benchmark
- Indicador de defasagem (ex.: "ultimo IPCA publicado: YYYY-MM")

## Plano de Implementacao por Fases

## Fase 0 - Alinhamento funcional (obrigatoria)
- Fechar regra de calculo IPCA com exemplos numericos
- Aprovar nomenclaturas de remuneracao (`SELIC_PERCENT`, `IPCA_PLUS_PRE`, etc.)
- Aprovar formato de coverage para serie mensal

Entrega: decisao documentada com 3-5 cenarios auditados.

## Fase 1 - Persistencia mensal IPCA
- Criar migration para `monthly_benchmark_rates`
- Atualizar `storage/schema.sql` com bloco idempotente
- Criar `MonthlyBenchmarkRatesRepository`

Entrega: CRUD basico + testes de repositorio.

## Fase 2 - Sync BACEN SELIC/IPCA
- Expandir `benchmark_sync.py`:
  - `SELIC` diario (serie 11) no fluxo atual
  - `IPCA` mensal (serie 433) em fluxo dedicado
- Normalizar parse de payload e validacao de shape
- Regras de bootstrap:
  - SELIC: semelhante ao CDI
  - IPCA: bootstrap por janela de meses

Entrega: sync confiavel com retries e erros claros.

## Fase 3 - Providers
- `SQLiteDailyRateProvider`: garantir suporte explicito a `SELIC`
- Novo `SQLiteMonthlyRateProvider` para `IPCA`
- Contratos de cobertura (`coverage_end` diario e mensal)

Entrega: providers com testes de contrato e edge cases.

## Fase 4 - Dominio e valuation
- Adicionar novos tipos de remuneracao no dominio
- Implementar motor SELIC_PERCENT
- Implementar motor IPCA conforme regra aprovada na Fase 0
- Definir comportamento para ausencia de dados:
  - tentar sync best-effort
  - se indisponivel, marcar incompleto com motivo claro

Entrega: calculo deterministico com testes de corretude.

## Fase 5 - API
- Extender endpoint de sync/coverage para SELIC e IPCA
- Garantir responses consistentes (camelCase)
- Validar erros 422/502 por benchmark e payload

Entrega: testes de API passando para os 3 benchmarks.

## Fase 6 - Frontend
- Atualizar Settings para cards CDI/SELIC/IPCA
- Mostrar coverage e status de cada serie
- Acionar sync por benchmark

Entrega: fluxo completo operavel pela UI.

## Fase 7 - Bootstrap e rollout
- `make reset-db`: manter CDI full
- Opcao adicional (avaliar): SELIC full e IPCA full no reset
- Teste de carga inicial e tempo total de bootstrap

Entrega: ambiente novo pronto com series historicas essenciais.

## Estrategia de Testes

### Unitarios
- Repositorio mensal IPCA
- Parse/normalizacao BACEN por serie
- Providers diarios/mensais
- Valuation SELIC e IPCA por cenarios controlados

### Integracao
- Endpoints sync/coverage para CDI, SELIC, IPCA
- Fluxo completo de revaluation apos sync

### Regressao
- Manter testes de CDI existentes
- Adicionar fixture real de SELIC
- Adicionar fixture real de IPCA (meses consecutivos)

### Corretude (obrigatorio)
- Bater resultados com calculos auditados manualmente
- Evitar testes apenas de consistencia interna

## Riscos e Mitigacoes

1. Ambiguidade de regra IPCA
- Mitigacao: Fase 0 obrigatoria antes de codar

2. Mudanca de formato de resposta BACEN
- Mitigacao: validacao robusta + mensagens de erro + testes com payload invalido

3. Defasagem de publicacao mensal (IPCA)
- Mitigacao: cobertura mensal explicita e status no frontend

4. Divergencia de arredondamento com bancos
- Mitigacao: `Decimal` end-to-end e snapshots auditados

## Criterios de Pronto

- Sync e coverage funcionam para CDI, SELIC e IPCA
- Valuation de novos tipos aprovado contra exemplos auditados
- API e frontend com status visivel de cobertura
- `make reset-db` deixa ambiente utilizavel sem setup manual
- Suite de testes relevante verde

## Backlog Opcional (depois)

- Auto-sync em lote para todos benchmarks no startup
- Politica de retentativa offline e fila local
- Painel de saude de dados BACEN (latencia, atraso, cobertura)

## Checklist de Execucao Futura

1. Revisar e aprovar Fase 0 (regra IPCA)
2. Abrir branch dedicada
3. Implementar Fase 1 e Fase 2
4. Rodar testes de repositorio/sync
5. Implementar Fase 3 e Fase 4
6. Rodar testes de dominio e regressao
7. Implementar Fase 5 e Fase 6
8. Rodar testes API/frontend
9. Validar `make reset-db`
10. Aprovar rollout
