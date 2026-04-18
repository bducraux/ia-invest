# IA-Invest

> Local-first investment portfolio ingestion, consolidation and AI-agent analysis.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

IA-Invest é um projeto open source para ingestão, consolidação e análise de portfólios de
investimento com apoio de agentes de IA.

O projeto é **local-first**: processamento local de arquivos, armazenamento em SQLite único
com separação lógica por portfólio, e exposição dos dados via protocolo MCP para uso com
clientes como o Claude Desktop.

Também inclui uma interface web em pasta separada, em `frontend/`, para manter o projeto
organizado sem acoplar o runtime Node.js ao backend Python.

---

## Quickstart

### 1. Instalar o uv e sincronizar dependências

Instale o uv (uma vez na máquina):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Sincronize o ambiente do projeto (cria/atualiza `.venv` automaticamente):

```bash
uv sync --extra dev
```

### 2. Inicializar o banco de dados

```bash
uv run python scripts/init_db.py
```

### 3. Criar um portfólio

Gere um portfólio a partir do template (interativo):

```bash
uv run python scripts/create_portfolio.py
```

No modo interativo, você escolhe o tipo (`generic`, `renda-variavel`, `renda-fixa`, `cripto`) e o nome.

Ou informe nome e tipo diretamente:

```bash
uv run python scripts/create_portfolio.py --type renda-variavel --name "Meu Portfólio"
```

O script cria `portfolios/<id>/` e ajusta `portfolio.yml` com o `id` e `name`.

Para adicionar novos tipos de portfólio, basta criar uma nova pasta em
`templates/<novo-tipo>/` contendo apenas `portfolio.yml`.
As subpastas `{inbox,staging,processed,rejected,exports}` são criadas
automaticamente pelo script.
Ela aparecerá automaticamente no menu interativo.

Fluxo manual (alternativo):

```bash
cp portfolio.example.yml portfolios/meu-portfolio/portfolio.yml
# edite portfolios/meu-portfolio/portfolio.yml conforme necessário
```

Crie as subpastas necessárias:

```bash
mkdir -p portfolios/meu-portfolio/{inbox,staging,processed,rejected,exports}
```

### 4. Colocar arquivos em `inbox/`

```bash
cp ~/Downloads/nota-corretagem.pdf portfolios/meu-portfolio/inbox/
```

### 5. Importar portfólio

```bash
uv run python scripts/import_portfolio.py --portfolio meu-portfolio
```

Importar todos os portfólios de uma vez:

```bash
uv run python scripts/import_all.py
```

### 6. Iniciar servidor MCP

```bash
uv run python -m mcp_server.server
```

O servidor MCP ficará acessível para clientes como o Claude Desktop via stdin/stdout.

### Comandos úteis com uv

```bash
uv run pytest
uv run ruff check .
uv run mypy .
```

### 7. Rodar o frontend (pasta separada)

Pré-requisito: Node.js 20.9+ (recomendado 22+) e npm 10+.

```bash
make frontend-install
make frontend-dev
```

A interface abrirá em http://localhost:3000.

Outros comandos úteis:

```bash
make frontend-lint
make frontend-test
make frontend-build
```

---

## Estrutura do projeto

```text
ia-invest/
├── portfolios/              # Portfólios de investimento
│   └── <portfolio-id>/
│       ├── portfolio.yml    # Manifesto de configuração
│       ├── inbox/           # Arquivos aguardando importação
│       ├── staging/         # Em pré-processamento
│       ├── processed/       # Importados com sucesso
│       ├── rejected/        # Rejeitados com log de erro
│       └── exports/         # Relatórios gerados
├── extractors/              # Parsers por fonte/layout
├── normalizers/             # Normalização e validação
├── domain/                  # Regras de negócio e modelos
├── storage/
│   ├── schema.sql           # Schema SQLite canônico
│   ├── migrations/          # Scripts de migração versionados
│   └── repository/          # Camada de acesso a dados
├── mcp_server/              # Servidor MCP local
│   ├── tools/               # Ferramentas expostas ao agente
│   └── resources/           # Recursos estáticos MCP
├── frontend/                # Frontend Next.js (UI web, separado do backend)
├── scripts/                 # Scripts operacionais
└── tests/                   # Testes automatizados
```

Veja [ARCHITECTURE.md](ARCHITECTURE.md) para detalhes de arquitetura e decisões técnicas.

---

## Portfólios suportados

Cada portfólio é uma entidade lógica independente. Exemplos típicos:

| ID               | Descrição                                      |
|------------------|------------------------------------------------|
| `renda-variavel` | Ações, FIIs, ETFs e BDRs                       |
| `renda-fixa`     | CDBs, LCIs, LCAs, Tesouro Direto               |
| `cripto`         | Criptoativos de exchanges                      |
| `previdencia`    | PGBL/VGBL                                      |
| `internacional`  | Ativos no exterior                             |

---

## Fontes de dados suportadas

| Fonte            | Extractor               | Status     |
|------------------|-------------------------|------------|
| B3 CSV/XLSX      | `B3CsvExtractor`        | ✅ Fase 2   |
| CSV de corretora | `BrokerCsvExtractor`    | ✅ Fase 2   |
| Binance CSV      | `BinanceCsvExtractor`   | ✅ Fase 2   |

---

## Ferramentas MCP disponíveis

| Tool                              | Descrição                                 |
|-----------------------------------|-------------------------------------------|
| `list_portfolios()`               | Lista todos os portfólios ativos          |
| `get_portfolio_summary(id)`       | Resumo de um portfólio                    |
| `get_portfolio_positions(id)`     | Posições abertas de um portfólio          |
| `get_portfolio_operations(id)`    | Operações de um portfólio                 |
| `compare_portfolios(ids)`         | Comparação entre portfólios               |
| `get_consolidated_summary()`      | Visão consolidada de todos os portfólios  |

---

## Contribuindo

Veja [ARCHITECTURE.md](ARCHITECTURE.md) para guias de extensão (novos extractors, novos
normalizers, etc.).

Pull Requests são bem-vindos. Por favor, inclua testes para qualquer nova funcionalidade.

---

## Licença

[MIT](LICENSE)
