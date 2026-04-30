"use client";

import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { DividendsPivotReport } from "@/features/dividends/dividends-pivot-report";
import { useDashboardScope } from "@/lib/dashboard-scope";
import {
  deriveOwnerLabel,
  mergeOperations,
} from "@/lib/portfolio-aggregation";
import {
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolios,
  usePortfolioSummaries,
  usePortfolioSummary,
} from "@/lib/queries";

const OPS_LIMIT = 5000;

export default function DividendsPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((p) => p.id);
  const activePortfolio = portfolios.find((p) => p.id === scope.portfolioId);

  const scopedOperationsQuery = usePortfolioOperations(
    scope.isGlobalScope ? undefined : scope.portfolioId,
    { limit: OPS_LIMIT, offset: 0 },
  );
  const globalOperationsQueries = usePortfolioOperationsList(
    scope.isGlobalScope ? portfolioIds : [],
    { limit: OPS_LIMIT, offset: 0 },
  );

  const scopedSummary = usePortfolioSummary(
    scope.isGlobalScope ? undefined : scope.portfolioId,
  );
  const globalSummaries = usePortfolioSummaries(
    scope.isGlobalScope ? portfolioIds : [],
  );

  const globalLoading = globalOperationsQueries.some((q) => q.isLoading);
  const globalError = globalOperationsQueries.find((q) => q.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalLoading
    : portfoliosQuery.isLoading || scopedOperationsQuery.isLoading;
  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalError
    : portfoliosQuery.error || scopedOperationsQuery.error;

  if (isLoading) {
    return (
      <>
        <TopBar title="Proventos" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Proventos recebidos" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Proventos" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Proventos recebidos"
            description="Falha ao carregar proventos. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Proventos" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Proventos recebidos"
            description="Selecione uma carteira válida na navegação lateral."
          />
        </main>
      </>
    );
  }

  const mergedOperations = scope.isGlobalScope
    ? mergeOperations(
        portfolios,
        globalOperationsQueries.map((q) => q.data?.operations ?? []),
      )
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
        ...deriveOwnerLabel(activePortfolio),
      }));

  const portfolioValueCents = scope.isGlobalScope
    ? globalSummaries.reduce((acc, q) => acc + (q.data?.marketValue ?? 0), 0) || null
    : scopedSummary.data?.marketValue ?? null;

  const title = scope.isGlobalScope ? "Proventos consolidados" : `Proventos - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Dividendos, JCP e rendimentos recebidos em todas as carteiras."
    : `Dividendos, JCP e rendimentos recebidos na carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Proventos" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <DividendsPivotReport
          operations={mergedOperations}
          portfolioValueCents={portfolioValueCents}
        />
      </main>
    </>
  );
}
