# Binance — Spot Trade History (CSV)

Histórico de trades à vista (Spot) da Binance, exportado via painel da
exchange. Ideal para a carteira `cripto`.

`source_type`: `binance_csv`

## Como baixar

1. Faça login em <https://www.binance.com/> (a versão Brasil também serve).
2. Vá em **Wallet → History → Spot Order History**
   (URL direta:
   <https://www.binance.com/en/my/orders/exchange/tradeorder>).
3. Selecione o intervalo de datas desejado.
4. Clique em **Export** (ou **Exportar**) e confirme o e-mail/2FA.
5. Baixe o ZIP gerado e extraia o CSV.
6. Mova o arquivo para `portfolios/<sua-carteira-cripto>/inbox/`.

> A Binance limita o intervalo de cada export a aproximadamente 6 meses.
> Para um histórico completo, gere vários arquivos sequenciais — o
> extractor processa todos juntos sem duplicar.

## Cabeçalhos suportados

O extractor aceita **inglês** ou **português** (igual ao painel da Binance):

| Inglês          | Português       | Significado                         |
|-----------------|-----------------|-------------------------------------|
| `Date(UTC)`     | `Tempo`         | Data/hora UTC do fill               |
| `Pair`          | `Par`           | Par negociado (ex.: `BTCUSDT`)      |
| `Side`          | `Lado`          | `BUY` ou `SELL`                      |
| `Price`         | `Preço`         | Preço unitário no par                |
| `Executed`      | `Executado`     | Quantidade da moeda base com sufixo  |
| `Amount`        | `Quantidade`    | Quantidade da moeda de cotação        |
| `Fee`           | `Taxa`          | Taxa cobrada (com sufixo de moeda)   |

## O que o extractor faz automaticamente

- **Deduplicação exata**: linhas idênticas em todas as colunas são removidas.
- **Agregação de fills parciais**: ordens partidas no order book em
  vários fills (mesmo timestamp + par + lado + preço) são consolidadas
  em um único registro.
- **Quote-leg**: para pares como `BTCUSDT`, o normalizador gera
  automaticamente uma operação contrária na moeda de cotação (`+BTC` /
  `-USDT` para uma compra, e vice-versa para uma venda). Pares contra
  BRL/USD/EUR não geram quote-leg (essas são moedas de funding).

## Pares e moedas reconhecidas como cotação

`USDT`, `BUSD`, `BRL`, `BTC`, `ETH`, `BNB`, `USD`, `EUR`. Outros pares
caem para a heurística do final do nome.

## Datas

Aceita os dois formatos comuns de export:

- `2024-04-13 21:13:14` (4 dígitos no ano)
- `24-04-13 21:13:14` (2 dígitos no ano — exports antigos)

A hora é descartada (datas são normalizadas para `YYYY-MM-DD`).
