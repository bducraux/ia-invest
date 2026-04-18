# ia-invest

Painel local-first para acompanhar carteiras de investimento brasileiras
(ações, FIIs, ETFs, renda fixa).

## Frontend

A interface web vive em [`frontend/`](./frontend) — Next.js (App Router),
TypeScript, Tailwind CSS, TanStack Query e Recharts.

```bash
cd frontend
npm install
npm run dev
```

Veja [frontend/README.md](./frontend/README.md) para detalhes de
convenções (centavos como inteiros, pt-BR, dark mode), scripts e
arquitetura.

## Backend

O backend Python (extractors → normalizers → domain → storage → MCP server)
será adicionado em PRs seguintes. Enquanto isso, o frontend roda com
fixtures locais em `frontend/src/mocks/data.ts`.
