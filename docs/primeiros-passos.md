# Primeiros passos com o IA-Invest

Este guia leva você do zero até ter o IA-Invest rodando localmente, com a
primeira carteira importada e a interface web no ar. Tempo estimado: 15
a 20 minutos.

> O IA-Invest é **local-first**: tudo roda na sua máquina, em arquivos
> seus, em um banco SQLite seu. Nenhum dado sai dali a menos que você
> conecte explicitamente a outro serviço (como o Claude Desktop via MCP).

---

## 1. Pré-requisitos

| Ferramenta | Versão mínima | Para quê                              |
|------------|---------------|----------------------------------------|
| Python     | 3.11+         | Backend, scripts e MCP server          |
| uv         | qualquer      | Gerenciador de dependências do backend |
| Node.js    | 20.9+ (22+ recomendado) | Frontend Next.js              |
| npm        | 10+           | Instalar dependências do frontend      |
| Make       | qualquer      | Atalhos para os comandos do dia-a-dia  |

Instalando o `uv` (uma vez por máquina):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. Instalação

```bash
git clone <url-do-repositorio>
cd ia-invest
make install         # instala deps do backend (uv sync --extra dev)
make init            # cria o banco SQLite vazio (ia_invest.db)
```

Pronto: o backend já tem tudo o que precisa para começar.

---

## 3. Criar sua primeira carteira

```bash
make create-portfolio
```

O script é interativo: pergunta o **tipo** (`renda-variavel`,
`renda-fixa`, `cripto`, `internacional`, `generic`) e o **nome**. Ele
cria a estrutura de pastas em `portfolios/<id>/`:

```text
portfolios/<id>/
├── portfolio.yml       # configuração (fontes habilitadas, regras)
├── inbox/              # arquivos aguardando importação
├── staging/            # em pré-processamento
├── processed/          # já importados com sucesso
├── rejected/           # falharam (ver import_errors no banco)
└── exports/            # relatórios gerados
```

Você pode criar quantas carteiras quiser. Uma sugestão prática:

| ID                  | Tipo             | O que vai dentro                  |
|---------------------|------------------|------------------------------------|
| `renda-variavel`    | `renda-variavel` | Ações, FIIs, ETFs e BDRs da B3     |
| `renda-fixa`        | `renda-fixa`     | CDB, LCI, LCA                      |
| `cripto`            | `cripto`         | Cripto em qualquer exchange        |
| `internacional`     | `internacional`  | Ativos no exterior (Avenue, IBKR)  |
| `previdencia-ibm`   | `generic`        | PGBL/VGBL da Fundação IBM          |

---

## 4. Colocar dados em `inbox/`

Cada carteira aceita um conjunto de **fontes de dados** (definido em
`portfolio.yml`, na lista `sources`). Veja a documentação completa em
[`docs/fontes-de-dados/`](fontes-de-dados/README.md):

- **Renda variável**: [B3 — Movimentação CSV/XLSX](fontes-de-dados/b3-csv.md),
  [CSV genérico de corretora](fontes-de-dados/broker-csv.md), ou
  [XLSX manual](fontes-de-dados/manual-xlsx.md)
- **Cripto**: [Binance Spot CSV](fontes-de-dados/binance-csv.md) ou
  [XLSX manual](fontes-de-dados/manual-xlsx.md)
- **Internacional**: [Avenue Apex PDF](fontes-de-dados/avenue-apex.md)
- **Renda fixa**: [CSV de aplicações](renda-fixa.md#csv-de-importação)
- **Previdência**: [Fundação IBM PDF](fontes-de-dados/previdencia-ibm.md)

Basta arrastar os arquivos baixados para
`portfolios/<sua-carteira>/inbox/`.

---

## 5. Importar

Para importar uma carteira específica:

```bash
uv run python scripts/import_portfolio.py --portfolio <id-da-carteira>
```

Para importar todas de uma vez:

```bash
make import-all
```

Após cada import, os arquivos são movidos automaticamente de `inbox/`
para `processed/`. Em caso de erro de parsing/validação, vão para
`rejected/` e os detalhes ficam na tabela `import_errors` do SQLite.

---

## 6. Sincronizar séries do BACEN (CDI e USDBRL)

Para que o cálculo de renda fixa atrelada ao CDI e a conversão de ativos
em USD funcionem corretamente, sincronize as séries históricas do BACEN
uma vez:

```bash
make sync-cdi-full       # CDI desde 2018-01-01 (≈ 2k linhas)
make sync-fx-full        # USDBRL PTAX desde 2018
```

Atualizações incrementais futuras são automáticas — o backend faz
best-effort sync quando uma requisição precisa de dados mais recentes.

> Atalho que faz tudo: `make reset-db` apaga o banco, recria do zero,
> reimporta todas as carteiras a partir de `processed/` e sincroniza
> CDI + USDBRL. Útil para começar limpo.

---

## 7. Subir a interface web

A interface roda em duas peças que precisam estar ativas ao mesmo tempo:

### Backend (FastAPI)

```bash
make api-server          # http://localhost:8010
```

### Frontend (Next.js)

Em outro terminal:

```bash
make frontend-install    # primeira vez apenas
make frontend-dev        # http://localhost:3000
```

Abra <http://localhost:3000> no navegador. Você verá o dashboard com a
visão consolidada das carteiras, posições, dividendos, renda fixa,
previdência, alertas de concentração, etc.

---

## 8. Conectar ao Claude Desktop (opcional)

O IA-Invest expõe um servidor MCP que permite usar o Claude Desktop como
agente analítico sobre suas carteiras. O arquivo `.mcp.json` na raiz do
projeto já está pronto:

```json
{
  "mcpServers": {
    "ia-invest": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"]
    }
  }
}
```

Para usar com o Claude Desktop:

1. Abra **Claude Desktop → Settings → Developer → Edit Config**.
2. Aponte para o `.mcp.json` deste projeto, **ou** copie o bloco
   `mcpServers.ia-invest` para o `claude_desktop_config.json` do seu
   sistema, ajustando o `cwd` para o caminho absoluto deste repositório.
3. Reinicie o Claude Desktop.

A partir daí, você pode fazer perguntas como:

> Como está a alocação da minha carteira de renda variável? Algum
> alerta de concentração?

### Memória entre conversas (skill `ia-invest`)

Se você usa a skill **`ia-invest`** do Claude Code (em
`.claude/skills/ia-invest/`), o agente mantém memória local entre
conversas em dois diretórios:

| Diretório              | O que guarda                                                  |
|------------------------|---------------------------------------------------------------|
| `.ia-invest-memory/`   | Notas vivas curtas: perfil de investidor, tese por ativo, eventos pendentes, visão consolidada |
| `relatorios/`          | Snapshots datados de análises completas (`relatorio-<id>-YYYY-MM-DD.md`) |

**Ambos são gitignorados por design** — contêm dados financeiros pessoais e
**nunca** devem ser comitados em forks públicos. Apenas o placeholder
`.gitkeep` é versionado para preservar a estrutura.

Se for o seu primeiro uso da skill, ela fará uma mini-entrevista (4–6
perguntas) para registrar seu perfil de investidor antes da primeira
análise de carteira. Esse perfil é atualizado automaticamente conforme
você expressa novas preferências em conversas posteriores.

---

## 9. Comandos do dia-a-dia

| Comando                            | O que faz                                                                |
|------------------------------------|---------------------------------------------------------------------------|
| `make import-all`                  | Importa tudo que estiver em `inbox/` de todas as carteiras                |
| `make portfolio-overview ARGS="--portfolio cripto --sort cost --hide-zero"` | Visão tabular completa de uma carteira |
| `make check-balance ARGS="--portfolio cripto --assets BTC,ETH"`             | Verifica saldo de ativos específicos   |
| `make adjust-balance ARGS="--portfolio cripto --asset BTC --real-quantity 0.55 --dry-run"` | Ajuste manual (com dry-run) de saldo divergente |
| `make sync-cdi`                    | Sincroniza CDI incremental (somente dias faltantes)                       |
| `make sync-fx`                     | Sincroniza FX incremental                                                 |
| `make reset-db`                    | Apaga e recria o banco do zero, reimporta tudo de `processed/`            |
| `make test`                        | Roda a suíte de testes                                                    |
| `make lint` / `make type-check`    | Linter (`ruff`) / type-check (`mypy`)                                     |

---

## 10. Solução de problemas

**Arquivo foi para `rejected/`** — abra o SQLite e consulte
`import_errors`:

```bash
sqlite3 ia_invest.db \
  "SELECT created_at, error_type, message FROM import_errors ORDER BY id DESC LIMIT 20;"
```

**Cota negativa em `positions`** — *isso é intencional* quando há
buracos no histórico (compras antigas que você ainda não importou). O
sistema preserva o saldo intermediário para sinalizar a inconsistência.
Veja `WALLET_MODEL.md` para detalhes.

**CDI ou USDBRL não atualizam** — verifique a conectividade com o BACEN.
O endpoint usado é `https://api.bcb.gov.br/dados/serie/...`. Se estiver
offline, os cálculos seguem com a cobertura atual e os valores recentes
ficam marcados como `isComplete = false`.

**Frontend mostra `--`** — o backend (FastAPI) provavelmente não está
rodando. Confira se `make api-server` está ativo em outro terminal e se
`NEXT_PUBLIC_API_URL` aponta para o endereço certo (padrão:
`http://localhost:8010`).

**Quero re-importar tudo do zero** — `make reset-db`. Atenção: isso
apaga o banco. Os PDFs/CSVs em `processed/` são copiados de volta
para `inbox/` automaticamente, então o histórico volta intacto após o
reimport.

---

## Próximos passos

- [Arquitetura](../ARCHITECTURE.md) — visão geral das camadas
- [Modelo de carteira](../WALLET_MODEL.md) — como `operations` vira `positions`
- [Renda fixa em detalhe](renda-fixa.md) — IR, CDI, lifecycle
- [Documentação de cada fonte](fontes-de-dados/README.md)
