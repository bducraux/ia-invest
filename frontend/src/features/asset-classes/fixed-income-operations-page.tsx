"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TopBar } from "@/components/layout/topbar";
import { EmptyState, PageHeader } from "@/components/layout/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/date";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL } from "@/lib/money";
import { getFixedIncomePositions, type FixedIncomePosition } from "@/lib/api";
import { deriveOwnerLabel } from "@/lib/portfolio-aggregation";
import { OwnerPortfolioBadge } from "@/components/portfolio/owner-portfolio-badge";
import { usePortfolios } from "@/lib/queries";

type FixedIncomeRow = FixedIncomePosition & {
  portfolioId: string;
  portfolioName: string;
  ownerId: string;
  ownerName: string;
};

function fixedIncomeDisplayName(position: FixedIncomePosition): string {
  return `${position.assetType} ${position.institution} ${position.productName}`.trim();
}

function remunerationLabel(position: FixedIncomePosition): string {
  if (position.remunerationType === "PRE") {
    return `Pré ${position.fixedRateAnnualPercent ?? 0}% a.a.`;
  }
  return `${position.benchmarkPercent ?? 0}% do CDI`;
}

export function FixedIncomeOperationsPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = useMemo(() => portfoliosQuery.data ?? [], [portfoliosQuery.data]);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);
  const visiblePortfolios = useMemo(
    () => (
      scope.isGlobalScope
        ? portfolios
        : activePortfolio
          ? [activePortfolio]
          : []
    ),
    [scope.isGlobalScope, portfolios, activePortfolio],
  );

  const positionQueries = useQueries({
    queries: visiblePortfolios.map((portfolio) => ({
      queryKey: ["fixed-income", portfolio.id, "operations-derived"],
      queryFn: () => getFixedIncomePositions(portfolio.id),
      enabled: Boolean(portfolio.id),
    })),
  });

  const isLoading = portfoliosQuery.isLoading || positionQueries.some((query) => query.isLoading);
  const error = portfoliosQuery.error || positionQueries.find((query) => query.error)?.error;

  const rows = useMemo<FixedIncomeRow[]>(
    () => visiblePortfolios
      .flatMap((portfolio, index) => {
        const owner = deriveOwnerLabel(portfolio);
        return (positionQueries[index]?.data ?? []).map((position) => ({
          ...position,
          portfolioId: portfolio.id,
          portfolioName: portfolio.name,
          ...owner,
        }));
      })
      .sort((left, right) => right.applicationDate.localeCompare(left.applicationDate)),
    [visiblePortfolios, positionQueries],
  );

  if (isLoading) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Operações - Renda fixa" description="Carregando aplicações de renda fixa..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Operações - Renda fixa" description="Falha ao carregar renda fixa. Verifique se a API está rodando." />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Operações - Renda fixa" description="Selecione uma carteira válida na navegação lateral." />
        </main>
      </>
    );
  }

  const title = scope.isGlobalScope
    ? "Operações - Renda fixa"
    : `Operações - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Lista consolidada das aplicações de renda fixa em todas as carteiras."
    : `Aplicações de renda fixa registradas na carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Operações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Aplicações registradas</CardTitle>
            <CardDescription>
              Como renda fixa ainda não possui trilha transacional completa, esta lista usa as aplicações cadastradas/importadas como eventos operacionais.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {rows.length === 0 ? (
              <EmptyState
                title="Nenhuma aplicação registrada"
                description="Cadastre ou importe uma aplicação para montar o histórico operacional de renda fixa."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data de aplicação</TableHead>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                    <TableHead>Ativo</TableHead>
                    <TableHead>Remuneração</TableHead>
                    <TableHead className="text-right">Aplicado</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={`${row.portfolioId}-${row.id}`}>
                      <TableCell>{formatDate(row.applicationDate)}</TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <OwnerPortfolioBadge
                            portfolioName={row.portfolioName}
                            ownerName={row.ownerName}
                          />
                        </TableCell>
                      ) : null}
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">{fixedIncomeDisplayName(row)}</span>
                          <span className="text-xs text-muted-foreground">{row.productName}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{remunerationLabel(row)}</TableCell>
                      <TableCell className="text-right font-medium">{formatBRL(row.principalAppliedBrl)}</TableCell>
                      <TableCell>{formatDate(row.maturityDate)}</TableCell>
                      <TableCell>
                        <Badge variant={row.status === "ACTIVE" ? "positive" : "outline"}>{row.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
