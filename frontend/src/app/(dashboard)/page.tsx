"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard } from "@/features/dashboard/kpi-card";
import { AllocationDonut } from "@/features/dashboard/allocation-donut";
import { AssetAllocationDonut } from "@/features/dashboard/asset-allocation-donut";
import { useDashboardScope } from "@/lib/dashboard-scope";
import {
  formatBRL,
  formatBRLSigned,
  formatPercent,
} from "@/lib/money";
import { formatDate } from "@/lib/date";
import {
  aggregateSummaries,
  mergeOperations,
  type OperationWithPortfolio,
} from "@/lib/portfolio-aggregation";
import {
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolioPositions,
  usePortfolioPositionsList,
  usePortfolios,
  usePortfolioSummaries,
  usePortfolioSummary,
} from "@/lib/queries";
import {
  Banknote,
  Coins,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function OverviewPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((portfolio) => portfolio.id);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  const scopedSummaryQuery = usePortfolioSummary(scope.isGlobalScope ? undefined : scope.portfolioId);
  const scopedOperationsQuery = usePortfolioOperations(scope.isGlobalScope ? undefined : scope.portfolioId, {
    limit: 6,
    offset: 0,
  });
  const scopedPositionsQuery = usePortfolioPositions(scope.isGlobalScope ? undefined : scope.portfolioId, true);

  const allSummaryQueries = usePortfolioSummaries(scope.isGlobalScope ? portfolioIds : []);
  const allOperationsQueries = usePortfolioOperationsList(scope.isGlobalScope ? portfolioIds : [], {
    limit: 6,
    offset: 0,
  });
  const allPositionsQueries = usePortfolioPositionsList(scope.isGlobalScope ? portfolioIds : [], true);

  const globalSummaryLoading = allSummaryQueries.some((query) => query.isLoading);
  const globalOperationsLoading = allOperationsQueries.some((query) => query.isLoading);
  const globalPositionsLoading = allPositionsQueries.some((query) => query.isLoading);
  const globalSummaryError = allSummaryQueries.find((query) => query.error)?.error;
  const globalOperationsError = allOperationsQueries.find((query) => query.error)?.error;
  const globalPositionsError = allPositionsQueries.find((query) => query.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalSummaryLoading || globalOperationsLoading || globalPositionsLoading
    : portfoliosQuery.isLoading
      || scopedSummaryQuery.isLoading
      || scopedOperationsQuery.isLoading
      || scopedPositionsQuery.isLoading;

  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalSummaryError || globalOperationsError || globalPositionsError
    : portfoliosQuery.error
      || scopedSummaryQuery.error
      || scopedOperationsQuery.error
      || scopedPositionsQuery.error;

  if (isLoading) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Visão consolidada" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Visão consolidada"
            description="Falha ao carregar dados da API. Verifique se o backend está rodando."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Carteira não encontrada"
            description="Selecione uma carteira válida na navegação lateral."
          />
        </main>
      </>
    );
  }

  if (scope.isGlobalScope && portfolios.length === 0) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Visão família"
            description="Nenhuma carteira cadastrada para consolidação."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !scopedSummaryQuery.data) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title={activePortfolio?.name ?? "Carteira"}
            description="Resumo indisponível para esta carteira."
          />
        </main>
      </>
    );
  }

  const globalSummaryInput = portfolios.map((portfolio, index) => ({
    portfolio,
    summary: allSummaryQueries[index]?.data,
  }));

  if (scope.isGlobalScope && globalSummaryInput.some((item) => !item.summary)) {
    return (
      <>
        <TopBar title="Visão geral" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Visão família"
            description="Não foi possível consolidar os dados de todas as carteiras."
          />
        </main>
      </>
    );
  }

  const globalConsolidated = scope.isGlobalScope
    ? aggregateSummaries(
        globalSummaryInput.map((item) => ({
          portfolio: item.portfolio,
          summary: item.summary!,
        })),
      )
    : null;

  const summary = scope.isGlobalScope ? globalConsolidated!.summary : scopedSummaryQuery.data!;

  const recent: OperationWithPortfolio[] = scope.isGlobalScope
    ? mergeOperations(
        portfolios,
        allOperationsQueries.map((query) => query.data?.operations ?? []),
      ).slice(0, 6)
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
      }));

  const contextTitle = scope.isGlobalScope ? "Visão família" : activePortfolio?.name ?? "Carteira";
  const contextDescription = scope.isGlobalScope
    ? `Consolidado em tempo real de ${portfolios.length} carteiras.`
    : `Resumo em tempo real da carteira ${activePortfolio?.name}.`;

  const quotePositions = scope.isGlobalScope
    ? allPositionsQueries.flatMap((query) => query.data ?? [])
    : (scopedPositionsQuery.data ?? []);

  return (
    <>
      <TopBar title="Visão geral" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={contextTitle} description={contextDescription} />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            title="Patrimônio atual"
            value={formatBRL(summary.marketValue)}
            subValue={`Caixa: ${formatBRL(summary.cashBalance)}`}
            icon={<Wallet className="h-4 w-4" />}
          />
          <KpiCard
            title="Total investido"
            value={formatBRL(summary.totalInvested)}
            subValue={
              summary.previdenciaTotalValue > 0
                ? `+ ${formatBRL(summary.previdenciaTotalValue)} previdência`
                : "Custo médio agregado"
            }
            icon={<Banknote className="h-4 w-4" />}
          />
          <KpiCard
            title="Resultado (não realizado)"
            value={formatBRLSigned(summary.unrealizedPnl)}
            trend={{
              label: formatPercent(summary.unrealizedPnlPct),
              positive: summary.unrealizedPnl >= 0,
            }}
            icon={<TrendingUp className="h-4 w-4" />}
          />
          <KpiCard
            title="Proventos no mês"
            value={formatBRL(summary.monthDividends)}
            trend={{
              label: formatPercent(summary.ytdReturnPct),
              positive: summary.ytdReturnPct >= 0,
            }}
            subValue="Retorno YTD"
            icon={<Coins className="h-4 w-4" />}
          />
        </div>

        <div
          className={cn(
            "grid grid-cols-1 gap-4",
            scope.isGlobalScope ? "lg:grid-cols-3" : "lg:grid-cols-2",
          )}
        >
          <Card>
            <CardHeader>
              <CardTitle className="text-base text-foreground">
                Alocação por ativo
              </CardTitle>
              <CardDescription>Top ativos por valor de mercado</CardDescription>
            </CardHeader>
            <CardContent>
              <AssetAllocationDonut positions={quotePositions} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base text-foreground">
                Alocação por classe
              </CardTitle>
              <CardDescription>Distribuição atual</CardDescription>
            </CardHeader>
            <CardContent>
              <AllocationDonut data={summary.allocation} />
            </CardContent>
          </Card>

          {scope.isGlobalScope ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-foreground">
                  Alocação por carteira
                </CardTitle>
                <CardDescription>Participação no patrimônio total</CardDescription>
              </CardHeader>
              <CardContent>
                <AllocationDonut data={globalConsolidated?.allocationByPortfolio ?? []} />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base text-foreground">
                Operações recentes
              </CardTitle>
              <CardDescription>Últimos lançamentos importados</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  <TableHead className="text-right">Preço</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((op) => (
                  <TableRow key={`${op.portfolioId}-${op.id}`}>
                    <TableCell>{formatDate(op.date)}</TableCell>
                    {scope.isGlobalScope ? (
                      <TableCell>
                        <Badge variant="outline">{op.portfolioName}</Badge>
                      </TableCell>
                    ) : null}
                    <TableCell className="font-medium">{op.assetCode}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          op.type === "COMPRA"
                            ? "positive"
                            : op.type === "VENDA"
                              ? "negative"
                              : "muted"
                        }
                      >
                        {op.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{op.quantity}</TableCell>
                    <TableCell className="text-right">
                      {formatBRL(op.unitPrice)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatBRL(op.total)}
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
