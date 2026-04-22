"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { Search } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SortableHead } from "@/components/ui/sortable-head";
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
  PREVIDENCIA: "Previdência",
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

type SortKey =
  | "assetCode"
  | "assetClass"
  | "quantity"
  | "avgPrice"
  | "marketPrice"
  | "marketValue"
  | "unrealizedPnlPct"
  | "weight";
type SortDir = "asc" | "desc";

function sortPositions(
  list: PositionWithPortfolio[],
  key: SortKey,
  dir: SortDir,
): PositionWithPortfolio[] {
  return [...list].sort((a, b) => {
    let cmp = 0;
    if (key === "assetCode" || key === "assetClass") {
      cmp = a[key].localeCompare(b[key]);
    } else {
      cmp = (a[key] as number) - (b[key] as number);
    }
    return dir === "asc" ? cmp : -cmp;
  });
}

function formatQuoteAge(ageSeconds?: number | null): string | null {
  if (ageSeconds == null || ageSeconds < 0) return null;
  if (ageSeconds < 60) return `${ageSeconds}s`;
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) return `${minutes}min`;
  return `${Math.floor(minutes / 60)}h`;
}

export default function PositionsPage() {
  const pageSize = 25;
  const scope = useDashboardScope();
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("ALL");
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "weight",
    dir: "desc",
  });
  const [pageByFilter, setPageByFilter] = useState<Record<string, number>>({});
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((p) => p.id);
  const activePortfolio = portfolios.find((p) => p.id === scope.portfolioId);

  const scopedPositionsQuery = usePortfolioPositions(
    scope.isGlobalScope ? undefined : scope.portfolioId,
    true,
  );
  const globalPositionsQueries = usePortfolioPositionsList(
    scope.isGlobalScope ? portfolioIds : [],
    true,
  );

  const globalLoading = globalPositionsQueries.some((q) => q.isLoading);
  const globalError = globalPositionsQueries.find((q) => q.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalLoading
    : portfoliosQuery.isLoading || scopedPositionsQuery.isLoading;
  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalError
    : portfoliosQuery.error || scopedPositionsQuery.error;

  const positions: PositionWithPortfolio[] = scope.isGlobalScope
    ? mergePositions(
        portfolios,
        globalPositionsQueries.map((q) => q.data ?? []),
      )
    : (scopedPositionsQuery.data ?? []).map((position) => ({
        ...position,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
      }));

  const availableClasses = useMemo(() => {
    const classes = new Set(positions.map((p) => p.assetClass));
    return Array.from(classes).sort();
  }, [positions]);

  const filteredPositions = useMemo(() => {
    let result = positions;

    if (classFilter !== "ALL") {
      result = result.filter((p) => p.assetClass === classFilter);
    }

    if (deferredSearch) {
      result = result.filter((p) =>
        [p.assetCode, p.name, p.assetClass, p.portfolioName]
          .join(" ")
          .toLowerCase()
          .includes(deferredSearch),
      );
    }

    return sortPositions(result, sort.key, sort.dir);
  }, [positions, classFilter, deferredSearch, sort]);

  function handleSort(key: string) {
    const typed = key as SortKey;
    setSort((prev) =>
      prev.key === typed
        ? { key: typed, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key: typed, dir: "desc" },
    );
  }

  const paginationKey = [
    scope.isGlobalScope ? "global" : scope.portfolioId ?? "",
    deferredSearch,
    classFilter,
    sort.key,
    sort.dir,
  ].join("|");
  const requestedPage = pageByFilter[paginationKey] ?? 1;

  const totalPages = Math.max(1, Math.ceil(filteredPositions.length / pageSize));
  const currentPage = Math.min(requestedPage, totalPages);
  const paginatedPositions = filteredPositions.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

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
            description="Selecione uma carteira válida na navegação lateral."
          />
        </main>
      </>
    );
  }

  const title = scope.isGlobalScope
    ? "Posições consolidadas"
    : `Posições - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Ativos consolidados de todas as carteiras da família."
    : `Ativos consolidados a partir das operações da carteira ${activePortfolio?.name}.`;

  const hasFilters = deferredSearch || classFilter !== "ALL";

  return (
    <>
      <TopBar title="Posições" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle className="text-base text-foreground">Carteira</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {filteredPositions.length} ativo
                  {filteredPositions.length === 1 ? "" : "s"}
                  {hasFilters ? ` encontrados de ${positions.length}` : " no resultado"}
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                {availableClasses.length > 1 && (
                  <select
                    value={classFilter}
                    onChange={(e) => setClassFilter(e.target.value)}
                    className="h-9 rounded-md border border-input bg-transparent px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="ALL">Todas as classes</option>
                    {availableClasses.map((cls) => (
                      <option key={cls} value={cls}>
                        {classLabels[cls] ?? cls}
                      </option>
                    ))}
                  </select>
                )}
                <div className="relative w-full sm:w-64">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar ativo, nome ou classe"
                    className="pl-9"
                  />
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead col="assetCode" sortKey={sort.key} direction={sort.dir} onSort={handleSort}>
                    Ativo
                  </SortableHead>
                  {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                  <SortableHead col="assetClass" sortKey={sort.key} direction={sort.dir} onSort={handleSort}>
                    Classe
                  </SortableHead>
                  <SortableHead col="quantity" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Qtd.
                  </SortableHead>
                  <SortableHead col="avgPrice" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Preço médio
                  </SortableHead>
                  <SortableHead col="marketPrice" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Cotação
                  </SortableHead>
                  <SortableHead col="marketValue" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Valor
                  </SortableHead>
                  <SortableHead col="unrealizedPnlPct" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Resultado
                  </SortableHead>
                  <SortableHead col="weight" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Peso
                  </SortableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedPositions.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={scope.isGlobalScope ? 9 : 8}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      Nenhum ativo encontrado para o filtro atual.
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedPositions.map((p) => (
                    <TableRow key={`${p.portfolioId}-${p.assetClass}-${p.assetCode}-${p.name}`}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">
                            {p.assetClass === "RENDA_FIXA" ? p.name : p.assetCode}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {p.assetClass === "RENDA_FIXA" ? p.assetCode : p.name}
                          </span>
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
                              {formatQuoteAge(p.quoteAgeSeconds)
                                ? ` · há ${formatQuoteAge(p.quoteAgeSeconds)}`
                                : ""}
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
                            className={p.unrealizedPnl >= 0 ? "text-positive" : "text-negative"}
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
                  ))
                )}
              </TableBody>
            </Table>
            <div className="flex flex-col gap-3 border-t border-border px-4 py-4 md:flex-row md:items-center md:justify-between">
              <p className="text-sm text-muted-foreground">
                Página {currentPage} de {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPageByFilter((prev) => ({
                      ...prev,
                      [paginationKey]: Math.max(1, currentPage - 1),
                    }))
                  }
                  disabled={currentPage <= 1}
                >
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPageByFilter((prev) => ({
                      ...prev,
                      [paginationKey]: Math.min(totalPages, currentPage + 1),
                    }))
                  }
                  disabled={currentPage >= totalPages}
                >
                  Próxima
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
