# Arquitetura — IA-Invest

## Visão geral

IA-Invest é um sistema **local-first** de ingestão e análise de portfólios de investimento.
O objetivo é transformar arquivos brutos de diferentes fontes (PDFs, CSVs, planilhas) em uma
base de dados SQLite consistente e consultável, acessível via servidor MCP para agentes de IA.

---

## Fluxo principal

```text
[portfolios/<portfolio>/inbox]
              ↓
      [Extractors / Parsers]
              ↓
    [Normalização / Validação]
              ↓
    [SQLite multi-portfólio]
              ↓
      [Services de domínio]
              ↓
       [Servidor MCP local]
              ↓
[Claude Desktop / outro cliente MCP]
              ↓
  [Consultas, análises e relatórios]
```

---

## Camadas e responsabilidades

### 1. Filesystem (`portfolios/`)

Ponto de entrada operacional. Cada subpasta representa um portfólio com seu manifesto YAML e
subpastas de ciclo de vida: `inbox → staging → processed / rejected`.

**Responsabilidade:** organizar arquivos brutos e registrar o estado de importação visualmente.

**Não é a fonte da verdade** — esta fica no banco.

---

### 2. Extractors (`extractors/`)

Cada extractor interpreta um layout de arquivo específico (B3 PDF, CSV de corretora, etc.) e
produz uma lista de registros brutos (dicionários) sem aplicar regras de negócio.

**Interface padrão:**

```python
class BaseExtractor:
    def can_handle(self, file_path: Path) -> bool: ...
    def extract(self, file_path: Path) -> list[dict]: ...
```

**Convenções:**
- Um extractor por layout/fonte.
- Erros de parsing por linha são registrados mas não interrompem o fluxo.
- O extractor não conhece o portfólio nem o banco.

---

### 3. Normalizers (`normalizers/`)

Recebem os registros brutos do extractor e os convertem para o modelo canônico de `Operation`
(ou outro modelo de domínio). Aplicam validações obrigatórias de campo, tipagem e formato.

**Interface padrão:**

```python
class BaseNormalizer:
    def normalize(self, raw_records: list[dict], portfolio_id: str) -> NormalizationResult: ...
```

`NormalizationResult` contém:
- `valid: list[Operation]` — registros válidos prontos para persistência
- `errors: list[NormalizationError]` — erros por registro

**Convenções:**
- Normalizers não leem nem escrevem no banco.
- Toda conversão de tipos (datas, valores monetários) fica aqui.
- Validações de negócio (ex: tipo de ativo permitido) ficam no domínio.

---

### 4. Domain (`domain/`)

Contém os modelos de domínio (dataclasses), regras de negócio determinísticas e cálculos
críticos que **nunca** devem ser delegados ao agente.

**Modelos principais:**
- `Portfolio` — representa um portfólio com seu manifesto
- `Operation` — operação normalizada (compra, venda, dividendo, etc.)
- `Position` — posição consolidada de um ativo em um portfólio
- `ImportJob` — registro de auditoria de uma importação

**Serviços de domínio:**
- `PortfolioService` — valida manifesto, verifica tipo de ativo permitido
- `PositionService` — calcula posição atual, preço médio, lucro/prejuízo realizado
- `DeduplicationService` — aplica deduplicação conforme chaves do manifesto

**Cálculos que ficam no domínio (nunca no agente):**
- Preço médio ponderado
- Posição consolidada
- Lucro/prejuízo realizado
- Deduplicação
- Classificação de eventos corporativos

---

### 5. Storage (`storage/`)

Camada de persistência usando SQLite único com separação lógica por `portfolio_id`.

**Schema central (`storage/schema.sql`):**
- `portfolios` — cadastro de portfólios
- `operations` — operações normalizadas
- `positions` — posições consolidadas (cache calculado)
- `import_jobs` — auditoria de importações
- `import_errors` — erros individuais por importação

**Repository pattern:**
- `PortfolioRepository` — CRUD de portfólios
- `OperationRepository` — inserção e consulta de operações
- `PositionRepository` — leitura e atualização de posições
- `ImportJobRepository` — criação e atualização de jobs de importação

**Convenções:**
- Todas as queries ficam nas classes de repositório.
- O MCP server **não** executa SQL diretamente.
- Migrations versionadas em `storage/migrations/` (formato: `NNNN_descricao.sql`).

---

### 6. MCP Server (`mcp_server/`)

Servidor MCP local que expõe ferramentas de negócio para agentes de IA (Claude Desktop, etc.).

**Filosofia:** expor tools orientadas ao domínio, não SQL livre.

**Tools disponíveis (`mcp_server/tools/`):**
- `list_portfolios` — lista portfólios ativos com metadados
- `get_portfolio_summary` — resumo de posição e PnL de um portfólio
- `get_portfolio_positions` — posições abertas com preço médio
- `get_portfolio_operations` — operações filtráveis por período/ativo
- `compare_portfolios` — comparação entre portfólios
- `get_consolidated_summary` — visão consolidada de todos os portfólios

**Convenções:**
- Respostas em JSON estável e documentado.
- Erros retornam mensagem amigável, nunca stack trace.
- Sem acesso direto ao filesystem pelo MCP.

---

## Decisões arquiteturais

| Decisão | Justificativa |
|---|---|
| SQLite único com `portfolio_id` | Facilita consultas consolidadas, manutenção do schema e evolução do MCP |
| Sem frontend inicial | Foco na base de dados, pipeline e MCP como camada de valor |
| Manifesto YAML por portfólio | Configuração declarativa, versionável e legível por humanos |
| Extractors separados por fonte | Isolamento de complexidade de parsing por layout |
| Domain services determinísticos | Garantia de resultados consistentes independente do agente |
| MCP como única interface para agentes | Controle do contrato de consulta, sem SQL livre |
| Filesystem como entrada, banco como verdade | Rastreabilidade de arquivos sem duplicar responsabilidade |

---

## Fluxo de importação detalhado

```text
scripts/import_portfolio.py --portfolio <id>
         │
         ├─ Lê portfolios/<id>/portfolio.yml
         ├─ Verifica arquivos em inbox/
         │
         ├─ Para cada arquivo:
         │   ├─ Move para staging/
         │   ├─ Cria ImportJob (status: processing)
         │   ├─ Seleciona Extractor compatível
         │   ├─ Extrai registros brutos
         │   ├─ Normaliza e valida
         │   ├─ Aplica deduplicação
         │   ├─ Persiste operations válidas
         │   ├─ Atualiza positions
         │   ├─ Fecha ImportJob (status: done | partial | failed)
         │   └─ Move arquivo para processed/ ou rejected/
         │
         └─ Loga resumo da importação
```

---

## Convenções de código

- Python 3.11+ com type hints completos.
- Dataclasses para modelos de domínio.
- `structlog` para logging estruturado.
- `pytest` para testes; fixtures em `tests/conftest.py`.
- Ruff para lint e formatação (`ruff check . && ruff format .`).
- Cada módulo expõe sua interface pública em `__init__.py`.

---

## Extensibilidade

### Adicionar novo extractor

1. Criar `extractors/meu_extractor.py` herdando de `BaseExtractor`.
2. Implementar `can_handle()` e `extract()`.
3. Registrar em `extractors/__init__.py`.
4. Adicionar testes em `tests/test_extractors/`.

### Adicionar nova fonte em `portfolio.yml`

```yaml
sources:
  - type: meu_extractor
    enabled: true
```

### Adicionar nova tool MCP

1. Criar função em `mcp_server/tools/`.
2. Registrar no `mcp_server/server.py`.
3. Documentar contrato de entrada/saída.

---

## Roadmap

| Marco | Entregável |
|---|---|
| A | Base do projeto + schema + portfólios + import por portfólio |
| B | Ingestão com 2 fontes + deduplicação + auditoria |
| C | Consolidação e relatórios de domínio |
| D | MCP completo para consultas operacionais |
| E | Integração com Claude Desktop e análise em linguagem natural |
