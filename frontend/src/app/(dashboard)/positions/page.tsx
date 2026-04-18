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
import {
  formatBRL,
  formatBRLSigned,
  formatPercent,
  formatQuantity,
} from "@/lib/money";
import { mergePositions, type PositionWithPortfolio } from "@/lib/portfolio-aggregation";
import {
  usePortfolioPositions,
  usePortfolioPositionsList,
  usePortfolios,
} from "@/lib/queries";

const classLabels: Record<string, string> = {
  ACAO: "Ação",
  FII: "FII",
  ETF: "ETF",
  RENDA_FIXA: "Renda Fixa",
  CAIXA: "Caixa",
  CRIPTO: "Cripto",
};

const quoteStatusLabel: Record<string, string> = {
  live: "Ao vivo",
  cache_fresh: "Atualizado",
  cache_stale: "Cache antigo",
  avg_fallback: "Preço médio",
};

const quoteStatusVariant: Record<string, "positive" | "muted" | "outline"> = {
  live: "positive",
  cache_fresh: "muted",
  cache_stale: "outline",
  avg_fallback: "outline",
};

function formatQuoteAge(ageSeconds?: number | null): string | null {
  if (ageSeconds == null || ageSeconds < 0) {
    return null;
  }
  if (ageSeconds < 60) {
    return `${ageSeconds}s`;
  }
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) {
    return `${minutes}min`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h`;
}

export default function PositionsPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((portfolio) => portfolio.id);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  const scopedPositionsQuery = usePortfolioPositions(scope.isGlobalScope ? undefined : scope.portfolioId, true);
  const globalPositionsQueries = usePortfolioPositionsList(scope.isGlobalScope ? portfolioIds : [], true);

  const globalLoading = globalPositionsQueries.some((query) => query.isLoading);
  const globalError = globalPositionsQueries.find((query) => query.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalLoading
    : portfoliosQuery.isLoading || scopedPositionsQuery.isLoading;
  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalError
    : portfoliosQuery.error || scopedPositionsQuery.error;

  if (isLoading) {
    return (
      <>
        <TopBar title="Posições" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Posições atuais" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Posições" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Posições atuais"
            description="Falha ao carregar posições. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Posições" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Posições atuais"
            description="Selecione um portfolio válido na navegação lateral."
          />
        </main>
      </>
    );
  }

  const positions: PositionWithPortfolio[] = scope.isGlobalScope
    ? mergePositions(
        portfolios,
        globalPositionsQueries.map((query) => query.data ?? []),
      )
    : (scopedPositionsQuery.data ?? []).map((position) => ({
        ...position,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Portfolio",
      }));

  const title = scope.isGlobalScope ? "Posições consolidadas" : `Posições - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Ativos consolidados de todas as carteiras da família."
    : `Ativos consolidados a partir das operações do portfolio ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Posições" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Carteira</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ativo</TableHead>
                  {scope.isGlobalScope ? <TableHead>Portfolio</TableHead> : null}
                  <TableHead>Classe</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  <TableHead className="text-right">Preço médio</TableHead>
                  <TableHead className="text-right">Cotação</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="text-right">Resultado</TableHead>
                  <TableHead className="text-right">Peso</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((p) => (
                  <TableRow key={`${p.portfolioId}-${p.assetCode}`}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">{p.assetCode}</span>
                        <span className="text-xs text-muted-foreground">{p.name}</span>
                      </div>
                    </TableCell>
                    {scope.isGlobalScope ? (
                      <TableCell>
                        <Badge variant="outline">{p.portfolioName}</Badge>
                      </TableCell>
                    ) : null}
                    <TableCell>
                      <Badge variant="muted">{classLabels[p.assetClass] ?? p.assetClass}</Badge>
                    </TableCell>
                    <TableCell className="text-right">{formatQuantity(p.quantity)}</TableCell>
                    <TableCell className="text-right">{formatBRL(p.avgPrice)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span>{formatBRL(p.marketPrice)}</span>
                        <Badge variant={quoteStatusVariant[p.quoteStatus] ?? "outline"}>
                          {quoteStatusLabel[p.quoteStatus] ?? p.quoteStatus}
                        </Badge>
                        {p.quoteStatus !== "avg_fallback" ? (
                          <span className="text-[11px] text-muted-foreground">
                            {p.quoteSource}
                            {formatQuoteAge(p.quoteAgeSeconds) ? ` · há ${formatQuoteAge(p.quoteAgeSeconds)}` : ""}
                          </span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatBRL(p.marketValue)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-col items-end leading-tight">
                        <span
                          className={
                            p.unrealizedPnl >= 0 ? "text-positive" : "text-negative"
                          }
                        >
                          {formatBRLSigned(p.unrealizedPnl)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatPercent(p.unrealizedPnlPct)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{formatPercent(p.weight)}</TableCell>
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
