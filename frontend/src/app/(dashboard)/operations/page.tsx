"use client";

import {
  Card,
  CardContent,
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
import { useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL, formatQuantity } from "@/lib/money";
import { formatDate } from "@/lib/date";
import {
  mergeOperations,
  type OperationWithPortfolio,
} from "@/lib/portfolio-aggregation";
import {
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolios,
} from "@/lib/queries";
import Link from "next/link";
import { Upload } from "lucide-react";

export default function OperationsPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((portfolio) => portfolio.id);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  const scopedOperationsQuery = usePortfolioOperations(scope.isGlobalScope ? undefined : scope.portfolioId, {
    limit: 100,
    offset: 0,
  });
  const globalOperationsQueries = usePortfolioOperationsList(scope.isGlobalScope ? portfolioIds : [], {
    limit: 100,
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
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Histórico de operações" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Histórico de operações"
            description="Falha ao carregar operações. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Histórico de operações"
            description="Selecione um portfolio válido na navegação lateral."
          />
        </main>
      </>
    );
  }

  const operations: OperationWithPortfolio[] = scope.isGlobalScope
    ? mergeOperations(
        portfolios,
        globalOperationsQueries.map((query) => query.data?.operations ?? []),
      )
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Portfolio",
      }));

  const total = scope.isGlobalScope
    ? globalOperationsQueries.reduce((acc, query) => acc + (query.data?.total ?? 0), 0)
    : scopedOperationsQuery.data?.total ?? 0;

  const title = scope.isGlobalScope
    ? "Histórico de operações consolidado"
    : `Histórico de operações - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Compras, vendas e proventos importados de todas as carteiras."
    : `Compras, vendas e proventos importados do portfolio ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Operações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title={title}
          description={description}
          actions={
            <Link
              href="/import"
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-transparent px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <Upload className="h-4 w-4" />
              Importar
            </Link>
          }
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">
              {total} operações
            </CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  {scope.isGlobalScope ? <TableHead>Portfolio</TableHead> : null}
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  <TableHead className="text-right">Preço unit.</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Origem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {operations.map((op) => (
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
                    <TableCell className="text-right">{formatQuantity(op.quantity)}</TableCell>
                    <TableCell className="text-right">{formatBRL(op.unitPrice)}</TableCell>
                    <TableCell className="text-right font-medium">
                      {formatBRL(op.total)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{op.source}</TableCell>
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
