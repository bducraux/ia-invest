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

```bash
# 1. instalar o uv (se ainda não tiver)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. instalar deps e iniciar banco
make install
make init

# 3. criar pelo menos um membro (dono dos portfólios)
uv run python scripts/create_member.py --id bruno --name "Bruno"

# 4. criar a primeira carteira (interativo) — pede o owner
make create-portfolio

# 5. dropar arquivos da corretora/exchange em portfolios/<owner>/<portfolio>/inbox/
#    e importar
make import-all

# 6. subir backend e frontend (em terminais separados)
make api-server         # http://localhost:8010
make frontend-install   # primeira vez apenas
make frontend-dev       # http://localhost:3000
```

> ⚠️ **Breaking change na versão Members.** O esquema agora exige
> `portfolios.owner_id` (FK para `members.id`) e o layout em disco passou
> de `portfolios/<portfolio>/` para `portfolios/<owner>/<portfolio>/`.
> Em ambientes existentes, faça `make reset-db`, recrie os membros e mova
> as pastas para a nova hierarquia (ou use
> `python scripts/transfer_portfolio_owner.py`).

**Guia completo, com troubleshooting e integração com o Claude Desktop:**
[**`docs/primeiros-passos.md`**](docs/primeiros-passos.md).

Para preparar arquivos de cada fonte (B3, Binance, Avenue, planilha
manual, etc.), veja [`docs/fontes-de-dados/`](docs/fontes-de-dados/README.md).

---

## Estrutura do projeto

```text
ia-invest/
├── portfolios/              # Portfólios de investimento
│   └── <owner-id>/          # Membro/dono (criado com scripts/create_member.py)
│       └── <portfolio-id>/
│           ├── portfolio.yml    # Manifesto (deve declarar owner_id idêntico ao folder pai)
│           ├── inbox/           # Arquivos aguardando importação
│           ├── staging/         # Em pré-processamento
│           ├── processed/       # Importados com sucesso
│           ├── rejected/        # Rejeitados com log de erro
│           ├── exports/         # Relatórios gerados
│           └── .cache/          # Cache opcional de extração (gitignored)
├── templates/               # Templates de portfólio (renda-variavel, renda-fixa,
│                            #   cripto, internacional, ...)
├── extractors/              # Parsers por fonte/layout (B3, Binance, Avenue, ...)
├── normalizers/             # Normalização e validação de operações
├── domain/                  # Regras de negócio (posições, valuation RF, FX, ...)
├── storage/
│   ├── schema.sql           # Schema SQLite canônico
│   ├── migrations/          # Scripts de migração versionados (NNNN_*.sql)
│   └── repository/          # Camada de acesso a dados (um repo por agregado)
├── mcp_server/              # Backend Python
│   ├── server.py            # Servidor MCP (stdin/stdout) p/ Claude Desktop
│   ├── http_api.py          # API HTTP (FastAPI) consumida pelo frontend
│   ├── tools/               # Ferramentas MCP expostas ao agente
│   ├── services/            # CDI/PTAX sync, quotes, fixed-income lifecycle
│   └── resources/           # Recursos estáticos MCP
├── frontend/                # Frontend Next.js (UI web, separado do backend)
├── scripts/                 # Scripts operacionais (import, sync CDI/PTAX, ...)
├── docs/                    # Documentação para usuários (PT-BR)
└── tests/                   # Testes automatizados
```

Veja [ARCHITECTURE.md](ARCHITECTURE.md) para detalhes de arquitetura e decisões técnicas.

---

## Portfólios suportados

Cada portfólio é uma entidade lógica independente. Exemplos típicos:

| ID               | Descrição                                      |
|------------------|------------------------------------------------|
| `renda-variavel` | Ações, FIIs, ETFs e BDRs                       |
| `renda-fixa`     | CDBs, LCIs e LCAs                              |
| `cripto`         | Criptoativos de exchanges                      |
| `previdencia`    | PGBL/VGBL                                      |
| `internacional`  | Ativos no exterior                             |

---

## Fontes de dados suportadas

| Fonte                              | `source_type`           | Documentação |
|------------------------------------|-------------------------|--------------|
| B3 — Movimentação CSV/XLSX         | `b3_csv`                | [b3-csv.md](docs/fontes-de-dados/b3-csv.md) |
| CSV genérico de corretora          | `broker_csv`            | [broker-csv.md](docs/fontes-de-dados/broker-csv.md) |
| Binance — Spot CSV                 | `binance_csv`           | [binance-csv.md](docs/fontes-de-dados/binance-csv.md) |
| Binance — Simple Earn CSV          | `binance_simple_earn`   | — |
| Avenue — Apex PDF (US)             | `avenue_apex_pdf`       | [avenue-apex.md](docs/fontes-de-dados/avenue-apex.md) |
| XLSX manual (bootstrap, B3)        | `manual_xlsx_b3`        | [manual-xlsx.md](docs/fontes-de-dados/manual-xlsx.md) |
| XLSX manual (bootstrap, cripto)    | `manual_xlsx_crypto`    | [manual-xlsx.md](docs/fontes-de-dados/manual-xlsx.md) |
| CSV de renda fixa (CDB/LCI/LCA)    | `fixed_income_csv`      | [renda-fixa.md](docs/renda-fixa.md) |
| Previdência — Fundação IBM (PDF)   | `previdencia_ibm_pdf`   | [previdencia-ibm.md](docs/fontes-de-dados/previdencia-ibm.md) |

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
