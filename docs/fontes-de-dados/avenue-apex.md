# Como baixar os PDFs Apex da Avenue

Este guia descreve o processo manual para obter o **Extrato mensal de
investimentos – Origem: Relatório Apex** da corretora
[Avenue Securities](https://avenue.us/) e prepará-los para importação no
IA-Invest.

O documento Apex é o extrato oficial da clearing (Apex Clearing Corporation,
EUA) e contém **todos** os eventos da carteira do mês — compras, vendas,
splits, spinoffs, dividendos, taxas e movimentações de caixa. É a fonte
canônica usada pelo extractor `avenue_apex_pdf`.


## Passo a passo

1. Faça login em <https://avenue.us/>.
2. Abra o menu **Relatórios**.
3. Selecione **Extrato mensal**.
4. No filtro **Origem**, escolha **Relatório Apex**.
5. Para cada mês desejado, clique em **Baixar PDF**.
6. **Renomeie** cada arquivo para o formato canônico
   `relatorio-apex-{mes}-{ano}.pdf`, com:
    - `mes` em português, **minúsculo, sem acento** (`janeiro`, `fevereiro`,
      `marco`, `abril`, `maio`, `junho`, `julho`, `agosto`, `setembro`,
      `outubro`, `novembro`, `dezembro`);
    - `ano` com 4 dígitos.

   Exemplos:
    - `relatorio-apex-janeiro-2026.pdf`
    - `relatorio-apex-marco-2024.pdf`
7. Mova os arquivos para o `inbox/` da carteira internacional
   correspondente (`portfolios/<minha-carteira-internacional>/inbox/`).
8. Rode a importação:

   ```bash
   make import-all
   # ou apenas a carteira internacional:
   uv run python scripts/import_portfolio.py --portfolio <minha-carteira-internacional>
   ```

## Política de cobertura

Recomenda-se baixar **todos os meses desde a abertura da conta**. O
extractor funciona corretamente mesmo se houver "buracos" entre meses (a
deduplicação por `(source, asset_code, operation_date, quantity)` evita
qualquer registro duplicado em re-imports).

Atenção ao **primeiro mês da conta**: é comum que esse extrato não traga
**PORTFOLIO SUMMARY**, porque ainda não havia posições liquidadas no
fechamento — as compras feitas no fim do mês só aparecem no extrato do
mês seguinte (após a settlement na Apex). Nesses extratos pioneiros o
extractor depende do **cache persistente nome→ticker** alimentado pelos
meses posteriores. O mecanismo já trata isso com um pré-passe que varre
TODOS os PDFs do `inbox/` antes da importação principal, então basta
manter os arquivos juntos quando importar pela primeira vez.


## Conteúdo coberto pelo extractor

| Seção do PDF              | Tratamento V1                           |
| ------------------------- | --------------------------------------- |
| `BUY / SELL TRANSACTIONS` | Compras (`buy`) viram operações em USD  |
| `BUY / SELL TRANSACTIONS` (com `STK SPLIT ON`) | Splits viram `split_bonus` (qty positiva, gross 0) |
| `PORTFOLIO SUMMARY` / `EQUITIES / OPTIONS` | Alimenta o cache `description→ticker`   |
| `DIVIDENDS AND INTEREST`  | Ignorado (V1 não rastreia dividendos)   |
| `FUNDS PAID AND RECEIVED` | Ignorado (caixa)                        |
| `FEES`, `INTEREST INCOME` | Ignorado                                |

Vendas (`SOLD`) ainda não são suportadas; aparecerão como linhas não
processadas se houver. Abra um issue se for o caso.
