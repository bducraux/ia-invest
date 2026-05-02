---
name: asset-metadata-enrich
description: >
  Skill que preenche o cadastro fiscal IRPF dos ativos da carteira do usuário (CNPJ e razão
  social oficial — `asset_name_oficial`) buscando os dados em fontes públicas: site da B3,
  página de Relações com Investidores (RI) de cada empresa/fundo, CVM, Receita Federal e
  páginas oficiais de ETFs/BDRs. Use SEMPRE que o usuário pedir para "preencher CNPJ",
  "completar cadastro IRPF", "buscar CNPJ dos ativos", "preencher dados do IRPF",
  "tem ativo sem CNPJ", "tem ativo sem nome", "enriquecer asset_metadata", ou quando o
  usuário reclamar que a tela do Simulador IR mostra ativos sem CNPJ ou sem razão social.
  IMPORTANTE: dados fiscais são sensíveis — confirme cada CNPJ com pelo menos uma fonte
  oficial antes de gravar; nunca invente dígitos.
---

# Asset Metadata Enrich — preencher CNPJ + razão social via IA

Você é responsável por **completar o cadastro fiscal** dos ativos da carteira do usuário no
IA-Invest, gravando `cnpj` e `asset_name_oficial` na tabela `asset_metadata` via REST API.
Esses campos são usados pelo Simulador IR (DIRPF) para preencher Bens e Direitos e Rendimentos
Isentos/Tributação Exclusiva — preencher errado significa declarar errado.

---

## Princípios inegociáveis

1. **Jamais invente um CNPJ.** Cada dígito tem que vir de fonte oficial. Se você não achar
   uma fonte confiável, **deixe em branco** e reporte ao usuário — nunca chute.
2. **Confirme com pelo menos uma fonte oficial** antes de gravar:
   - B3 (`https://www.b3.com.br/`) para ações, FIIs, FIAGRO, ETFs, BDRs.
   - Página de RI da empresa/administradora (Itaú RI, JHSF RI, BTG Pactual RI, etc.).
   - CVM (`https://sistemas.cvm.gov.br/`) para fundos.
   - Receita Federal (consulta CNPJ pública) só como segunda checagem.
3. **`asset_name_oficial` é a razão social exata** que aparece no documento da empresa
   (ex.: `ITAÚSA S.A.`, `BTG PACTUAL FUNDO DE INVESTIMENTO IMOBILIÁRIO – LOGÍSTICO`). Não
   abrevie, não traduza, não tire acentos.
4. **CNPJ é gravado como string formatada** `NN.NNN.NNN/NNNN-NN` (com pontos, barra e hífen).
   O backend aceita só dígitos também, mas mantenha o padrão formatado.
5. **BDRs**: o CNPJ é o do **emissor brasileiro do BDR** (ex.: Banco Bradesco para BDRs Nível
   I patrocinados pelo Bradesco), não o CNPJ da empresa estrangeira.
6. **Stablecoins, cripto, renda fixa, previdência** não têm linha em `asset_metadata` — ignore.
7. Sempre que tiver dúvida, **pergunte ao usuário** com a evidência que você encontrou — é
   melhor perguntar do que gravar errado.

---

## Fluxo padrão (ponta a ponta)

### 1. Descobrir o que falta

Chame o endpoint local de listagem com filtros:

```bash
curl -s 'http://localhost:8010/api/asset-metadata?missing_cnpj=true' | jq
curl -s 'http://localhost:8010/api/asset-metadata?missing_name=true' | jq
```

Cada item retornado tem este shape (camelCase):

```json
{
  "assetCode": "ITSA4",
  "cnpj": null,
  "assetClass": "acao",
  "assetNameOficial": null,
  "sectorCategory": null,
  "sectorSubcategory": null,
  "siteRi": null,
  "source": "auto",
  "notes": null,
  "dataSource": "auto",
  "lastSyncedAt": null
}
```

Junte os dois resultados em uma lista única `ativos_a_enriquecer`.

### 2. ANTES de pesquisar, consulte o catálogo versionado

Existe um catálogo CSV versionado dividido por classe de ativo:

```
data/asset_catalog/acoes.csv      ← acao
data/asset_catalog/fiis.csv       ← fii + fiagro
data/asset_catalog/criptos.csv    ← cripto
data/asset_catalog/stocks.csv     ← stocks (US equities)
```

Schema canônico (8 colunas): `ticker,cnpj,razao_social,asset_class,sector_category,sector_subcategory,site_ri,fonte`.

**Sempre leia o arquivo da classe certa primeiro** (`read_file`) e cheque se o ticker pendente já
está lá. Se estiver:

- Use os dados do catálogo direto no PATCH (sem busca web).
- Se houver `siteRi` no catálogo, **use essa URL como fonte primária** antes de fazer `web_search`.
- Se a `notes` de uma linha existente do banco estiver em conflito com o catálogo, **avise
  o usuário** — pode ser ticker renomeado (ex.: `GALG11` foi renomeado para `GARE11`,
  ambos com o mesmo CNPJ; nesse caso o catálogo deve ter as DUAS linhas).

### 3. Para cada ativo NOVO, identificar a fonte certa pela classe

| `assetClass` | Onde buscar (em ordem de preferência) |
|---|---|
| `acao` | Site de RI da empresa → B3 → CVM. CNPJ = CNPJ da companhia listada. |
| `fii` / `fiagro` | Página da B3 do fundo (`/produtos-e-servicos/negociacao/renda-variavel/fundos-de-investimentos/...`) ou ficha CVM. CNPJ = CNPJ do **fundo** (não do administrador). |
| `etf` | Página do gestor (BlackRock iShares, Itaú Asset, BTG, etc.) ou B3. CNPJ = CNPJ do fundo ETF. |
| `bdr` | Página da B3 do BDR. CNPJ = CNPJ do **emissor brasileiro** do BDR. |

Use `web_search` (queries do tipo `"ITSA4" CNPJ site:b3.com.br` ou `"HGLG11" CNPJ
"fundo de investimento imobiliário"`) e depois `web_fetch` na URL mais oficial do top-3.

### 3. Validar antes de gravar

Antes de qualquer PATCH:

- O CNPJ tem 14 dígitos depois de remover pontuação?
- Encontrou o mesmo CNPJ em **pelo menos 1 fonte oficial** (B3, RI ou CVM)?
- A razão social bate com o ticker (mesma empresa/fundo, não um homônimo)?
- Para FII/ETF: confirmou que é o CNPJ do **fundo**, não do administrador?
- Se o ticker já está no seed: o CNPJ que você descobriu **bate com o seed**? Se diverge,
  PARE e investigue — ou o seed está errado, ou sua fonte é menos confiável.

Se qualquer resposta for "não", **pule** o ativo e adicione na lista de pendências para
revisão manual do usuário.

### 4. Gravar via PATCH

```bash
curl -s -X PATCH 'http://localhost:8010/api/asset-metadata/ITSA4' \
  -H 'Content-Type: application/json' \
  -d '{
        "cnpj": "61.532.644/0001-15",
        "assetNameOficial": "ITAÚSA S.A."
      }'
```

Campos do payload (todos opcionais — só envie o que você apurou):

- `cnpj` — string formatada `NN.NNN.NNN/NNNN-NN` ou `null` para limpar.
- `assetNameOficial` — razão social exata.
- `assetClass` — `"acao" | "fii" | "fiagro" | "bdr" | "etf" | "cripto" | "stocks"`. Só envie se tiver
  certeza que a inferência automática estava errada (ex.: ticker `XPTO11` que é FIAGRO,
  não FII).
- `sectorCategory` / `sectorSubcategory` — taxonomia setorial (ex.: `"Tijolo"` / `"Lajes Corporativas"`
  para FII; `"Financeiro"` / `"Bancos"` para ação). Use os mesmos rótulos do catálogo.
- `siteRi` — URL canônica da página de Relações com Investidores.
- `notes` — texto curto opcional para registrar a fonte (ex.: `"B3, consulta em 2026-04-30"`).

A resposta devolve o registro completo atualizado. O endpoint cria a linha se ainda não
existir.

### 5. Atualizar o catálogo versionado

**Para ativos novos descobertos via web (não vindos do catálogo)**, sempre adicione uma linha
ao arquivo da classe certa em `data/asset_catalog/` para que o próximo usuário do projeto
não precise refazer a pesquisa. Formato (8 colunas):

```csv
ticker,cnpj,razao_social,asset_class,sector_category,sector_subcategory,site_ri,fonte
ITSA4,61.532.644/0001-15,ITAÚSA S.A.,acao,Financeiro,Holdings,https://www.itausa.com.br/ri,B3 + RI Itausa 2026-04
```

Dicas:

- Vá ao arquivo correto: `acoes.csv` (acao), `fiis.csv` (fii/fiagro), `criptos.csv` (cripto),
  `stocks.csv` (stocks).
- Ordene as linhas alfabeticamente por ticker.
- Se o ticker foi renomeado (ex.: `GALG11` → `GARE11`), **mantenha as duas linhas** com o
  mesmo CNPJ — o ticker antigo preserva o histórico de operações.
- Alternativa programática: depois de gravar via PATCH, rode
  `uv run python scripts/dump_asset_metadata_seed.py --write` para regenerar todos os CSVs
  do catálogo a partir do banco.

Avise o usuário no fim: *"Adicionei N linhas ao catálogo (`data/asset_catalog/...`) — considere
commitar para ajudar futuros usuários."*

### 6. Reportar ao usuário

Ao terminar, mostre:

1. **Quantos ativos foram enriquecidos** (CNPJ + nome).
2. **Quais ficaram pendentes** e por quê (sem fonte confiável, ticker descontinuado, etc.).
3. **Diferenças entre o que estava antes e o que foi gravado**, quando aplicável (ex.:
   classe IRPF reclassificada de `fii` para `fiagro`).
4. **Pedido explícito de confirmação** para os casos duvidosos antes de gravar.

---

## Exemplo de execução completa (uma pendência)

```text
Usuário: "Tem ativo sem CNPJ no IRPF, dá pra preencher?"

1. GET /api/asset-metadata?missing_cnpj=true
   → [{ "assetCode": "ITSA4", "assetClass": "acao", ... }]

2. web_search: "ITSA4 CNPJ site:b3.com.br"
   → top-1: página da B3 do ITSA4

3. web_fetch dessa página
   → "ITAÚSA S.A. - CNPJ: 61.532.644/0001-15"

4. Confirmação cruzada com web_fetch em ri.itausa.com.br
   → "Itaúsa S.A. - CNPJ 61.532.644/0001-15"

5. PATCH /api/asset-metadata/ITSA4
   { "cnpj": "61.532.644/0001-15", "assetNameOficial": "ITAÚSA S.A." }

6. Resposta ao usuário:
   "Preenchi ITSA4 → ITAÚSA S.A. (61.532.644/0001-15), confirmado em B3 e RI Itaúsa."
```

---

## Anti-padrões (NUNCA faça)

- ❌ Gravar CNPJ de "primeiro resultado do Google" sem checar fonte oficial.
- ❌ Usar CNPJ do **administrador** de um FII (ex.: BTG Pactual Asset) no lugar do CNPJ do
  fundo.
- ❌ Traduzir/abreviar a razão social ("Itaúsa S/A" em vez de "ITAÚSA S.A.").
- ❌ Preencher CNPJ para criptos, renda fixa ou previdência (essas não têm linha em
  `asset_metadata`).
- ❌ Inferir CNPJ por "padrão similar" a outro ativo da mesma empresa.
- ❌ Sobrescrever um CNPJ já preenchido sem perguntar — se `cnpj != null` na resposta do
  GET, não toque sem confirmação explícita do usuário.

---

## Pré-requisitos

- API local rodando: `make api-server` (default `http://localhost:8010`).
- Sync inicial já executado: `make sync-asset-catalog` (cria as linhas a partir do catálogo
  e do ledger; o legado `make bootstrap-asset-metadata` ainda funciona como alias).
- Tabela `asset_metadata` populada: se `GET /api/asset-metadata` retornar lista vazia, peça
  para o usuário rodar `make sync-asset-catalog` antes.
