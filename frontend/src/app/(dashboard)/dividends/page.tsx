"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { DividendsBarChart } from "@/features/dividends/dividends-bar-chart";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL } from "@/lib/money";
import { formatDate } from "@/lib/date";
import {
  aggregateDividendsByMonth,
  deriveOwnerLabel,
  mergeOperations,
  toDividendEntries,
} from "@/lib/portfolio-aggregation";
import { OwnerPortfolioBadge } from "@/components/portfolio/owner-portfolio-badge";
import {
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolios,
} from "@/lib/queries";

export default function DividendsPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((portfolio) => portfolio.id);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  const scopedOperationsQuery = usePortfolioOperations(scope.isGlobalScope ? undefined : scope.portfolioId, {
    limit: 400,
    offset: 0,
  });
  const globalOperationsQueries = usePortfolioOperationsList(scope.isGlobalScope ? portfolioIds : [], {
    limit: 400,
    offset: 0,
  });

  const globalLoading = globalOperationsQueries.some((query) => query.isLoading);
  const globalError = globalOperationsQueries.find((query) => query.error)?.error;

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
        globalOperationsQueries.map((query) => query.data?.operations ?? []),
      )
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
        ...deriveOwnerLabel(activePortfolio),
      }));

  const dividends = toDividendEntries(mergedOperations);
  const dividendsByMonth = aggregateDividendsByMonth(dividends);
  const total = dividendsByMonth.reduce((acc, month) => acc + month.amount, 0);

  const title = scope.isGlobalScope ? "Proventos consolidados" : `Proventos - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Dividendos e JCP recebidos em todas as carteiras."
    : `Dividendos e JCP recebidos na carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Proventos" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">
              Histórico mensal
            </CardTitle>
            <CardDescription>
              Total no período: <strong className="text-foreground">{formatBRL(total)}</strong>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DividendsBarChart data={dividendsByMonth} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Lançamentos</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dividends.map((d) => (
                  <TableRow key={`${d.portfolioId}-${d.id}`}>
                    <TableCell>{formatDate(d.date)}</TableCell>
                    {scope.isGlobalScope ? (
                      <TableCell>
                        <OwnerPortfolioBadge
                          portfolioName={d.portfolioName}
                          ownerName={d.ownerName}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell className="font-medium">{d.assetCode}</TableCell>
                    <TableCell>
                      <Badge variant="muted">{d.type}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium text-positive">
                      {formatBRL(d.amount)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
