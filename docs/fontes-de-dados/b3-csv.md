# B3 — Movimentação CSV/XLSX

A B3 disponibiliza, na área do investidor, um relatório com todas as
**negociações** (compras e vendas) executadas pelas corretoras em seu CPF.
Esse relatório é a fonte mais confiável para popular uma carteira de renda
variável (`renda-variavel`).

`source_type`: `b3_csv`

## Como baixar

1. Acesse <https://www.investidor.b3.com.br/> e faça login com a conta gov.br.
2. No menu, vá em **Extratos e Informativos → Negociação**.
3. Selecione o intervalo desejado (recomendado: desde a data da primeira
   operação na bolsa).
4. Clique em **Exportar para Excel** (gera `.xlsx`) ou **Baixar CSV**.
5. Mova o arquivo para `portfolios/<sua-carteira>/inbox/`.

## Formato esperado

O extractor reconhece o cabeçalho oficial da B3 (português, com acento).
Colunas obrigatórias:

| Coluna                     | Descrição                                       |
|----------------------------|-------------------------------------------------|
| `Data do Negócio`          | Data da operação (DD/MM/AAAA ou ISO 8601)       |
| `Tipo de Movimentação`     | `Compra` ou `Venda`                              |
| `Código de Negociação`     | Ticker (ex.: `PETR4`, `VISC11`); o sufixo `F` de fracionário é removido automaticamente |
| `Quantidade`               | Quantidade de ações/cotas                        |
| `Preço`                    | Preço unitário em BRL                            |
| `Valor`                    | Valor total em BRL                               |

Colunas opcionais usadas pelo extractor: `Mercado`, `Prazo/Vencimento`,
`Instituição` (vira o campo `broker`).

## Pontos de atenção

- O relatório de **Negociação** lista apenas trades — dividendos, JCP,
  bonificações e desdobramentos **não** estão nele. Para esses, a B3 expõe
  outro relatório (Eventos Corporativos), ainda **não** suportado nesta
  versão.
- Linhas vazias e linhas com `Tipo de Movimentação` desconhecido vão para
  `import_errors` em vez de quebrar o import.
- Tickers fracionários (`PETR4F`) são automaticamente normalizados para
  o ticker principal (`PETR4`).
