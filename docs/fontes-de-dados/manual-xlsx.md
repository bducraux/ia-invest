# XLSX manual (bootstrap)

Planilha Excel preenchida manualmente para "semear" o IA-Invest com o
histórico de operações que você já tem registrado em outro lugar (uma
plataforma antiga, sua própria contabilidade, etc.). Útil quando a
corretora/exchange não disponibiliza um export em formato suportado, ou
quando você quer carregar dados anteriores ao período coberto pelo
relatório oficial.

Existem dois extractors com o mesmo formato de cabeçalho, diferenciados
pelo tipo de ativo padrão:

| Extractor           | `source_type`         | Carteira típica   | Tipo de ativo padrão |
|---------------------|-----------------------|-------------------|----------------------|
| `ManualXlsxB3`      | `manual_xlsx_b3`      | `renda-variavel`  | inferido pelo ticker |
| `ManualXlsxCrypto`  | `manual_xlsx_crypto`  | `cripto`          | `crypto`             |

## Habilitando na carteira

Edite `portfolios/<sua-carteira>/portfolio.yml` e adicione a fonte:

```yaml
sources:
  - type: manual_xlsx_b3        # ou manual_xlsx_crypto
    enabled: true
```

## Templates prontos

Cópias vazias com cabeçalho e algumas linhas de exemplo estão em:

- [`docs/samples/manual_xlsx_b3.xlsx`](../samples/manual_xlsx_b3.xlsx)
- [`docs/samples/manual_xlsx_crypto.xlsx`](../samples/manual_xlsx_crypto.xlsx)

Copie o arquivo, apague as linhas de exemplo e preencha com seus dados.
Não renomeie as colunas.

## Cabeçalho obrigatório

A primeira linha deve conter exatamente as colunas abaixo (a ordem é
livre, mas os nomes devem bater). Uma coluna opcional `Data de
modificação` pode aparecer antes de `Ativo`, mas é ignorada.

| Coluna              | Descrição                                                             |
|---------------------|------------------------------------------------------------------------|
| `Ativo`             | Ticker (ex.: `PETR4`, `VISC11`, `BTC`, `ETH`)                          |
| `Tipo`              | Operação (ver tabela abaixo)                                           |
| `Data da transação` | Data da operação (ver formatos aceitos)                                |
| `Quantidade`        | Número de cotas/ações/unidades. Aceita decimais (ex.: `0,00309` ou `0.00309`) |
| `Preço`             | Preço unitário em BRL                                                  |
| `Valor total`       | Valor total da operação em BRL                                         |
| `Custodiante`       | Corretora ou exchange (texto livre, ex.: `INTER DTVM`, `BINANCE BRASIL`) |

## Tipos de operação aceitos (coluna `Tipo`)

### `manual_xlsx_b3` (renda variável)

| Texto na planilha               | Operação resultante |
|----------------------------------|---------------------|
| `Compra`                        | `buy`               |
| `Venda`                         | `sell`              |
| `Transferência de Custódia`     | `transfer_in`       |
| `Ajustes de Posição Inicial`    | `transfer_in`       |
| `Bonificação`                   | `transfer_in`       |
| `Desdobramento`                 | `transfer_in`       |

Acentos são opcionais (`Transferencia de Custodia` também funciona).

### `manual_xlsx_crypto`

| Texto na planilha | Operação resultante |
|-------------------|---------------------|
| `Compra`          | `buy`               |
| `Venda`           | `sell`              |

## Formatos de data aceitos

A coluna `Data da transação` aceita:

- Data nativa do Excel (célula formatada como data) — recomendado
- `YYYY-MM-DD` (ISO 8601, ex.: `2024-04-15`)
- `DD/MM/YYYY` (ex.: `15/04/2024`)
- `DD-MM-YYYY`
- Número serial do Excel (ex.: `46059` → `2026-02-06`)

## Formato monetário

A coluna `Preço` e `Valor total` aceitam:

- Números puros (ex.: `1146.49` ou `1.146,49`)
- Com prefixo `R$` (ex.: `R$ 1.146,49` ou `R$ 1146.49`)
- O caractere `R$` e espaços são ignorados

## Aliases de ticker (apenas crypto)

Para o extractor de cripto, alguns tickers são automaticamente normalizados:

- `RNDR` → `RENDER`
- `MATIC` → `POL` (renomeação oficial da Polygon em 2023)

Se você notar que outro ticker precisa ser aliasado, abra um issue.

## Custos / dividendos

Esta fonte **não** suporta colunas de taxas, dividendos ou JCP. Se você
precisa registrar esses eventos, use o
[CSV genérico de corretora](broker-csv.md) que aceita `taxas` e tipos
como `dividend`/`jcp`.
