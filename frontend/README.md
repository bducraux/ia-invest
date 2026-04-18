# IA-Invest — Frontend

Painel local-first para acompanhar uma carteira de investimentos brasileira
(ações, FIIs, ETFs, renda fixa). Construído com Next.js (App Router),
TypeScript, Tailwind CSS v4, TanStack Query e Recharts.

> **Status:** scaffold inicial. Esta versão usa fixtures locais em
> `src/mocks/data.ts`. A integração com API do backend Python será adicionada
> em uma etapa posterior.

## Requisitos

- Node.js 20+ (recomendado 22+)
- npm 10+

## Como rodar

```bash
cd frontend
npm install
npm run dev
```

Abra <http://localhost:3000>.

## Scripts

| Comando         | O que faz                                  |
| --------------- | ------------------------------------------ |
| `npm run dev`   | Servidor de desenvolvimento (HMR).         |
| `npm run build` | Build de produção.                         |
| `npm run start` | Roda o build em produção.                  |
| `npm run lint`  | Executa ESLint (config Next).              |
| `npm run test`  | Roda os testes unitários (Vitest).         |

## Convenções

### Dinheiro como inteiros (centavos)

Todos os valores monetários são armazenados como **inteiros em centavos**
(R$ 1,00 = `100`) — espelhando o backend. Nunca use `parseFloat` em moeda
nem aritmética de ponto flutuante.

Helpers em `@/lib/money`:

- `formatBRL(cents)` → `R$ 1.234,56`
- `formatBRLCompact(cents)` → `R$ 1,2 mi`
- `formatBRLSigned(cents)` → `+R$ 1,50` / `−R$ 1,50`
- `formatPercent(0.1234)` → `+12,34%`

O tipo `Cents` é uma branded type (`number & { __brand: "cents" }`) para
evitar somar centavos com reais por engano.

### Idioma e datas

Toda a UI é em **pt-BR**. Datas são formatadas via `formatDate`
(`@/lib/date`) no padrão brasileiro (`dd/mm/aaaa`). Sobre o fio, datas
trafegam como ISO (`YYYY-MM-DD`).

### Tema

Dark mode é o padrão. O usuário pode alternar pelo botão na barra superior;
`next-themes` aplica a classe `dark` no `<html>`.

## Estrutura

```
src/
  app/                # Next App Router (páginas + layouts)
    (dashboard)/      # Grupo de rotas com sidebar persistente
  components/
    layout/           # Sidebar, topbar, page header
    ui/               # Componentes base (button, card, table, ...)
  features/           # Componentes específicos por feature
    dashboard/        # KPI cards, gráficos da visão geral
    dividends/        # Gráfico de proventos
  lib/                # money, date, utils
  mocks/              # Fixtures locais (substituídas pelo backend)
  types/              # Tipos do domínio
tests/                # Testes Vitest
```

## Próximos passos

1. Subir uma API FastAPI reusando `domain/` e `storage/repository/` do
   backend Python.
2. Gerar tipos TypeScript a partir do `openapi.json` da API.
3. Substituir os imports de `@/mocks/data` por uma camada de cliente HTTP
  tipada para os endpoints reais.
4. Servir o build estático do frontend pela própria FastAPI para
   distribuição em comando único (`python -m ia_invest`).
