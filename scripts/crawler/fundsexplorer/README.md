# Crawler de FIIs e FIAGROs — FundsExplorer

Script único que extrai a lista completa de Fundos Imobiliários (FIIs) e
FIAGROs listados na B3 a partir do FundsExplorer
([`/funds`](https://www.fundsexplorer.com.br/funds) e
[`/fiagros`](https://www.fundsexplorer.com.br/fiagros)),
enriquecida com nome completo, CNPJ e tipo (segmento), e grava direto no
catálogo canônico do projeto:
[`data/asset_catalog/fiis.csv`](../../../data/asset_catalog/fiis.csv).

## Visão geral

```
        ┌────────────────────────────┐   ┌──────────────────────────────┐
        │ fundsexplorer.com.br/funds │   │ fundsexplorer.com.br/fiagros │
        └─────────────┬──────────────┘   └──────────────┬───────────────┘
                      │ 1 req                           │ 1 req
                      └───────────────┬─────────────────┘
                                      ▼
                ┌────────────────────────────────────┐
                │  generate_fiis_csv.py              │
                │  passo 1: parseia ambas listagens  │
                │           (asset_class por fonte)  │
                │  passo 2: abre página de cada      │
                │           fundo em paralelo        │
                └─────────────┬──────────────────────┘
                              │ ~700+ requisições paralelas
                              ▼
                ┌──────────────────────────────────────────┐
                │  data/asset_catalog/fiis.csv             │
                │  ticker,cnpj,razao_social,asset_class,   │
                │  sector_category,sector_subcategory,     │
                │  site_ri,fonte                           │
                └──────────────────────────────────────────┘
```

## Schema de saída

O crawler grava no schema canônico do catálogo de ativos (ver
[`data/asset_catalog/README.md`](../../../data/asset_catalog/README.md)):

| Coluna               | Origem                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `ticker`             | `[data-element="ticker-box-title"]` da listagem                                             |
| `cnpj`               | `<div class="headerTicker__content__cnpj">` da página individual                            |
| `razao_social`       | `.tickerBox__desc` (listagem) → fallback `headerTicker__content__name`                      |
| `asset_class`        | `fii` ou `fiagro` — definido automaticamente pela listagem de origem (`/funds` vs `/fiagros`) |
| `sector_category`    | parte antes do `:` em `.tickerBox__type` (ex.: `Tijolo`)                                    |
| `sector_subcategory` | parte depois do `:` (ex.: `Lajes Corporativas`)                                             |
| `site_ri`            | nunca preenchido pelo crawler (fica para a skill IA / edição manual)                        |
| `fonte`              | `FundsExplorer YYYY-MM` (mês da última gravação)                                            |

## Merge não-destrutivo

**O crawler nunca sobrescreve uma célula já preenchida** no CSV
destino. Se a skill IA preencheu o `site_ri` de um ticker, ou você
ajustou manualmente uma `razao_social`, rodar o crawler de novo
preserva tudo isso. Ele só preenche células vazias.

## Características

- **Concorrência controlada:** 8 threads em paralelo + jitter
  aleatório de 0.3–0.8s entre requests.
- **Checkpoint a cada 25 fundos:** o CSV destino é regravado
  periodicamente. Se o script for interrompido, ao rodar de novo
  ele continua de onde parou.
- **Retry com backoff exponencial:** até 3 tentativas para erros HTTP/rede.
- **Fallback de extração:** se os seletores CSS principais falharem,
  cai para regex sobre o texto bruto.
- **Falhas isoladas:** tickers que falharem após todas as tentativas
  vão para `fiis_failed.csv` (ao lado deste script) e **não** entram
  no `fiis.csv`. Basta rodar de novo para reprocessá-los.
- **Pulo rápido:** tickers já com CNPJ no CSV destino não disparam
  fetch novamente.

## Pré-requisitos

- Python 3.11+ + dependências do projeto (`requests`, `beautifulsoup4`).

## Como rodar

```bash
# do repo root
uv run python scripts/crawler/fundsexplorer/generate_fiis_csv.py

# ou apontando para outro arquivo:
uv run python scripts/crawler/fundsexplorer/generate_fiis_csv.py /tmp/teste.csv
```

## Tempo estimado

| Etapa                       | Requisições  | Tempo aprox.  |
| --------------------------- | ------------ | ------------- |
| Listagens (passo 1)         | 2            | ~3 segundos   |
| Enriquecimento (passo 2)    | até ~700+    | 2 a 5 minutos |

Em runs subsequentes, só os tickers ainda sem CNPJ fazem fetch.

## Ajustes finos

No topo de `generate_fiis_csv.py`:

```python
MAX_WORKERS          = 8       # threads em paralelo
SLEEP_MIN, SLEEP_MAX = 0.30, 0.80  # delay aleatório entre requests (s)
CHECKPOINT_EVERY     = 25      # frequência de gravação no disco
MAX_RETRIES          = 3       # tentativas em caso de erro
TIMEOUT              = 30      # timeout HTTP (s)
```

Se o site começar a retornar 429 (rate limit), reduza `MAX_WORKERS`
para 4 e aumente `SLEEP_MAX` para 1.5.

Para adicionar uma nova listagem do FundsExplorer (ex.: outro tipo de
fundo), basta adicionar uma tripla `(asset_class, list_url, fund_url_tpl)`
em `SOURCES` no topo do script.

## Troubleshooting

**Muitos fundos em `fiis_failed.csv`**
Indica instabilidade ou rate limiting do site. Espere alguns minutos
e rode de novo — só os tickers ainda sem CNPJ serão reprocessados.

**Nenhum fundo extraído da listagem**
A estrutura HTML mudou. Inspecione o site e ajuste os seletores
(`tickerBox__title`, `tickerBox__desc`, `tickerBox__type`).
