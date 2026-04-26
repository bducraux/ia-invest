# Documentação do IA-Invest

Toda a documentação do projeto, em português.

## Comece por aqui

- **[Primeiros passos](primeiros-passos.md)** — guia completo de
  instalação, criação da primeira carteira, importação, frontend e
  Claude Desktop. Se você nunca rodou o IA-Invest, comece por este.

## Como entrar com seus dados

- **[Fontes de dados](fontes-de-dados/README.md)** — uma página por
  formato suportado (B3, Binance, Avenue, etc.) com instruções de
  download/preparação e descrição das colunas.
- **[Arquivos de exemplo](samples/)** — templates vazios prontos para
  copiar e preencher.

## Conceitos

- **[Renda fixa](renda-fixa.md)** — como o IA-Invest trata CDB/LCI/LCA:
  cálculo de IR, fonte da taxa CDI (BACEN), lifecycle de aplicações,
  formato CSV de importação.

## Documentos de arquitetura (em inglês)

Os documentos abaixo são internos e estão em inglês para alinhamento
com a base de código:

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — visão geral da arquitetura
- [`WALLET_MODEL.md`](../WALLET_MODEL.md) — modelo `operations` →
  `positions`
- [`CLAUDE.md`](../CLAUDE.md) — guia para agentes de IA trabalhando
  neste repositório
