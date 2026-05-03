# GitHub Copilot — Instruções do projeto IA-Invest

Este projeto é um gerenciador local-first de portfólio de investimentos brasileiro.
Antes de qualquer tarefa não-trivial, **leia [`CLAUDE.md`](../CLAUDE.md) na raiz** — ele
contém o contexto canônico do projeto: arquitetura, comandos `make`, modelo de dados
(SQLite + valores em **centavos como inteiros**), pipeline de extractors/normalizers/domain
e convenções da camada FastAPI/Next.js.

## Convenções inegociáveis (resumo)

- **Valores monetários são inteiros em centavos** em todo lugar (Python, SQLite, frontend).
  Nunca use `float`. Use `Decimal` em cálculos intermediários e `ROUND_HALF_EVEN` na
  conversão final.
- **MCP/HTTP nunca escrevem SQL cru** — toda consulta passa por `storage/repository/`.
- **Domínio é determinístico** (`PositionService`, `FixedIncomeValuationService`, etc.) —
  não delegue cálculos a LLM.
- **Datas no fio são ISO `YYYY-MM-DD`**. Apresentação em `pt-BR` é responsabilidade do
  frontend (`@/lib/date`).
- **Pydantic responses do `mcp_server/http_api.py` usam camelCase**; tools MCP retornam
  snake_case verbatim.

## Skills sincronizadas com Claude Code

Este repositório suporta **dois agentes de IA em paralelo**: GitHub Copilot e Claude Code.
Cada skill é **duplicada** — uma versão otimizada para cada ferramenta — para extrair o
máximo de cada uma sem comprometer a paridade de comportamento.

| Skill | Arquivo Claude (canônico) | Arquivo(s) Copilot |
|---|---|---|
| `ia-invest` (analista de portfólio) | `.claude/skills/ia-invest/SKILL.md` | `.github/chatmodes/ia-invest.chatmode.md` + `.github/instructions/ia-invest-trigger.instructions.md` |

Referências compartilhadas (lidas pelos dois agentes, **não duplicar**):
- `.claude/skills/ia-invest/references/macro-contexto.md` — contexto macro/setorial.

### ⚠️ Regra de sincronização (OBRIGATÓRIA)

**Ao alterar qualquer arquivo de skill, atualize obrigatoriamente o(s) par(es) na outra
ferramenta na mesma mudança.** Divergências silenciosas entre as duas versões são
consideradas bug.

Exemplos:
- Mudou um princípio inegociável no `SKILL.md` do Claude? Reflita no chatmode do Copilot.
- Adicionou uma nova MCP tool ao fluxo no chatmode? Reflita no `SKILL.md`.
- Adicionou/removeu vocabulário de auto-invoke na `description` do Claude? Atualize o
  `instructions/ia-invest-trigger.instructions.md` correspondente.

A divergência aceita é apenas **forma** (frontmatter, voz adaptada à ferramenta, instruções
de UI específicas — ex.: "use o painel de Chat do VS Code"). A **intenção** e as **regras**
têm que casar.

Quando tiver dúvida se uma mudança precisa propagar, propague — é mais barato sincronizar a
mais do que descobrir drift depois.

## Modos de chat customizados

- **`ia-invest`** — analista de portfólio que consome o MCP server local. Selecione no
  seletor de modo do painel de Chat sempre que for falar de carteira, posições, ativos,
  dividendos, alocação ou alertas. A instrução em `ia-invest-trigger.instructions.md`
  detecta esse vocabulário e sugere a troca proativamente.
