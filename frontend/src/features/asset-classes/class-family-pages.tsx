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
import { EmptyState, PageHeader } from "@/components/layout/page-header";
import { AllocationDonut } from "@/features/dashboard/allocation-donut";
import { ValueAllocationDonut, type ValueAllocationSlice } from "@/features/dashboard/value-allocation-donut";
import { formatDate } from "@/lib/date";
import { useDashboardScope } from "@/lib/dashboard-scope";
import {
  formatBRL,
  formatBRLSigned,
  formatPercent,
  formatQuantity,
} from "@/lib/money";
import {
  mergeOperations,
  mergePositions,
  type OperationWithPortfolio,
  type PositionWithPortfolio,
} from "@/lib/portfolio-aggregation";
import {
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolioPositions,
  usePortfolioPositionsList,
  usePortfolios,
} from "@/lib/queries";
import type { ClassFamily } from "@/lib/asset-class-config";
import {
  aggregateRendaVariavelExposure,
  buildRendaVariavelTypeSlices,
} from "@/features/asset-classes/renda-variavel-analytics";

const FAMILY_META: Record<ClassFamily, {
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  operationsDescription: string;
}> = {
  RENDA_VARIAVEL: {
    title: "Renda variável",
    description: "Ações, FIIs e ETFs consolidados por classe.",
    emptyTitle: "Nenhuma posição de renda variável",
    emptyDescription: "Importe operações de ações, FIIs ou ETFs para começar.",
    operationsDescription: "Compras, vendas, dividendos, JCP e eventos corporativos consolidados.",
  },
  CRIPTO: {
    title: "Criptomoedas",
    description: "Posições e movimentações consolidadas de ativos digitais.",
    emptyTitle: "Nenhuma posição em cripto",
    emptyDescription: "Importe movimentações da exchange para consolidar esta visão.",
    operationsDescription: "Compras e vendas consolidadas de ativos digitais.",
  },
  PREVIDENCIA: {
    title: "Previdência",
    description: "Snapshots consolidados de previdência por carteira.",
    emptyTitle: "Nenhuma posição de previdência",
    emptyDescription: "Importe extratos de previdência para consolidar esta visão.",
    operationsDescription: "A aplicação hoje consolida snapshots; movimentações detalhadas ainda não são expostas nesta classe.",
  },
  INTERNACIONAL: {
    title: "Internacional",
    description: "Posições e movimentações de ativos negociados no exterior (Avenue, etc).",
    emptyTitle: "Nenhuma posição internacional",
    emptyDescription: "Importe extratos da Avenue (CSV) para consolidar esta visão.",
    operationsDescription: "Compras de ações, ETFs e REITs nos EUA convertidas para BRL via PTAX.",
  },
};

const RENDA_VARIAVEL_EXPOSURE_CHART = {
  minWeightForOwnSlice: 0.02,
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
  if (ageSeconds == null || ageSeconds < 0) return null;
  if (ageSeconds < 60) return `${ageSeconds}s`;
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) return `${minutes}min`;
  return `${Math.floor(minutes / 60)}h`;
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function buildExposureSlices(
  data: ValueAllocationSlice[],
  options: {
    minWeightForOwnSlice: number;
  },
): ValueAllocationSlice[] {
  const { minWeightForOwnSlice } = options;

  if (data.length === 0) {
    return data;
  }

  const majorSlices = data.filter((item) => item.weight >= minWeightForOwnSlice);
  const minorSlices = data.filter((item) => item.weight < minWeightForOwnSlice);

  if (minorSlices.length === 0) {
    return data;
  }

  const othersValue = minorSlices.reduce((sum, item) => sum + item.value, 0);
  const othersWeight = minorSlices.reduce((sum, item) => sum + item.weight, 0);

  if (majorSlices.length === 0) {
    return [
      {
        label: "Outros",
        value: othersValue,
        weight: othersWeight,
      },
    ];
  }

  return [
    ...majorSlices,
    {
      label: "Outros",
      value: othersValue,
      weight: othersWeight,
    }
  ];
}

function useClassFamilyData(classFamily: ClassFamily) {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((portfolio) => portfolio.id);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  const scopedPositionsQuery = usePortfolioPositions(
    scope.isGlobalScope ? undefined : scope.portfolioId,
    true,
    classFamily,
  );
  const globalPositionsQueries = usePortfolioPositionsList(
    scope.isGlobalScope ? portfolioIds : [],
    true,
    classFamily,
  );

  const scopedOperationsQuery = usePortfolioOperations(
    scope.isGlobalScope ? undefined : scope.portfolioId,
    { limit: 5000, offset: 0, assetClass: classFamily },
  );
  const globalOperationsQueries = usePortfolioOperationsList(
    scope.isGlobalScope ? portfolioIds : [],
    { limit: 5000, offset: 0, assetClass: classFamily },
  );

  const globalLoading = globalPositionsQueries.some((query) => query.isLoading)
    || globalOperationsQueries.some((query) => query.isLoading);
  const globalError = globalPositionsQueries.find((query) => query.error)?.error
    || globalOperationsQueries.find((query) => query.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalLoading
    : portfoliosQuery.isLoading || scopedPositionsQuery.isLoading || scopedOperationsQuery.isLoading;
  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalError
    : portfoliosQuery.error || scopedPositionsQuery.error || scopedOperationsQuery.error;

  const positions: PositionWithPortfolio[] = scope.isGlobalScope
    ? mergePositions(
        portfolios,
        globalPositionsQueries.map((query) => query.data ?? []),
      )
    : (scopedPositionsQuery.data ?? []).map((position) => ({
        ...position,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
      }));

  const scopeMarketValue = positions.reduce((sum, position) => sum + position.marketValue, 0);
  const positionsWithScopeWeight = positions.map((position) => ({
    ...position,
    weight: scopeMarketValue > 0 ? position.marketValue / scopeMarketValue : 0,
  }));

  const operations: OperationWithPortfolio[] = scope.isGlobalScope
    ? mergeOperations(
        portfolios,
        globalOperationsQueries.map((query) => query.data?.operations ?? []),
      )
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
      }));

  return {
    scope,
    portfolios,
    activePortfolio,
    isLoading,
    error,
    positions: positionsWithScopeWeight,
    operations,
  };
}

function renderState(
  title: string,
  description: string,
  pageTitle: string,
) {
  return (
    <>
      <TopBar title={pageTitle} />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />
      </main>
    </>
  );
}

export function ClassFamilyOverviewPage({ classFamily }: { classFamily: ClassFamily }) {
  const meta = FAMILY_META[classFamily];
  const {
    scope,
    activePortfolio,
    isLoading,
    error,
    positions,
    operations,
  } = useClassFamilyData(classFamily);

  if (isLoading) {
    return renderState(meta.title, "Carregando dados do backend...", meta.title);
  }

  if (error) {
    return renderState(meta.title, "Falha ao carregar dados. Verifique se a API está rodando.", meta.title);
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return renderState(meta.title, "Selecione uma carteira válida na navegação lateral.", meta.title);
  }

  const totalMarketValue = positions.reduce((sum, position) => sum + position.marketValue, 0);
  const totalUnrealized = positions.reduce((sum, position) => sum + position.unrealizedPnl, 0);
  const monthDividends = operations
    .filter((operation) => operation.type === "DIVIDENDO" || operation.type === "JCP")
    .reduce((sum, operation) => sum + operation.total, 0);
  const topPositions = [...positions].sort((left, right) => right.marketValue - left.marketValue).slice(0, 8);
  const recentOperations = operations.slice(0, 10);
  const rendaVariavelTypeSlices = classFamily === "RENDA_VARIAVEL"
    ? buildRendaVariavelTypeSlices(positions)
    : [];
  const rendaVariavelAssetExposure = classFamily === "RENDA_VARIAVEL"
    ? aggregateRendaVariavelExposure(positions)
    : [];
  const rendaVariavelExposureSlices = classFamily === "RENDA_VARIAVEL"
    ? buildExposureSlices(rendaVariavelAssetExposure.map((item) => ({
        label: item.assetCode,
        value: item.marketValue,
        weight: item.weight,
      })), RENDA_VARIAVEL_EXPOSURE_CHART)
    : [];

  const title = scope.isGlobalScope
    ? `${meta.title} consolidada`
    : `${meta.title} - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? meta.description
    : `${meta.title} da carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title={meta.title} />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <div className="grid gap-4 md:grid-cols-4">
          <SummaryCard label="Patrimônio atual" value={formatBRL(totalMarketValue)} />
          <SummaryCard label="Ativos consolidados" value={String(positions.length)} />
          <SummaryCard label="Resultado não realizado" value={formatBRLSigned(totalUnrealized)} />
          <SummaryCard
            label={classFamily === "RENDA_VARIAVEL" ? "Proventos observados" : "Eventos observados"}
            value={classFamily === "RENDA_VARIAVEL" ? formatBRL(monthDividends) : String(operations.length)}
          />
        </div>

        {classFamily === "RENDA_VARIAVEL" ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-foreground">Composição por subtipo</CardTitle>
                <CardDescription>Mostra a proporção entre ações, FIIs e ETFs dentro da renda variável.</CardDescription>
              </CardHeader>
              <CardContent>
                <AllocationDonut data={rendaVariavelTypeSlices} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base text-foreground">Exposição agregada por ativo</CardTitle>
                <CardDescription>
                  Soma o valor de mercado do mesmo ticker para mostrar a exposição total por ativo.
                  Ativos com menos de 2% são agrupados em Outros.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ValueAllocationDonut data={rendaVariavelExposureSlices} />
              </CardContent>
            </Card>
          </div>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">{classFamily === "RENDA_VARIAVEL" ? "Maior exposição por ativo" : "Maiores posições"}</CardTitle>
            <CardDescription>
              {classFamily === "RENDA_VARIAVEL"
                ? "Consolida o mesmo ativo entre carteiras para facilitar a leitura de exposição total."
                : meta.emptyDescription}
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {classFamily === "RENDA_VARIAVEL" ? (
              rendaVariavelAssetExposure.length === 0 ? (
                <EmptyState title={meta.emptyTitle} description={meta.emptyDescription} />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ativo</TableHead>
                      {scope.isGlobalScope ? <TableHead className="text-right">Carteiras</TableHead> : null}
                      <TableHead className="text-right">Qtd.</TableHead>
                      <TableHead className="text-right">Patrimônio</TableHead>
                      <TableHead className="text-right">Peso</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rendaVariavelAssetExposure.map((position) => (
                      <TableRow key={position.assetCode}>
                        <TableCell>
                          <div className="flex flex-col">
                            <span className="font-medium">{position.assetCode}</span>
                            <span className="text-xs text-muted-foreground">{position.name}</span>
                          </div>
                        </TableCell>
                        {scope.isGlobalScope ? (
                          <TableCell className="text-right">{position.portfolioCount}</TableCell>
                        ) : null}
                        <TableCell className="text-right">{formatQuantity(position.quantity)}</TableCell>
                        <TableCell className="text-right font-medium">{formatBRL(position.marketValue)}</TableCell>
                        <TableCell className="text-right">{formatPercent(position.weight)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )
            ) : topPositions.length === 0 ? (
              <EmptyState title={meta.emptyTitle} description={meta.emptyDescription} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ativo</TableHead>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                    <TableHead className="text-right">Qtd.</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                    <TableHead className="text-right">Resultado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {topPositions.map((position) => (
                    <TableRow key={`${position.portfolioId}-${position.assetCode}`}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">{position.assetCode}</span>
                          <span className="text-xs text-muted-foreground">{position.name}</span>
                        </div>
                      </TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <Badge variant="outline">{position.portfolioName}</Badge>
                        </TableCell>
                      ) : null}
                      <TableCell className="text-right">{formatQuantity(position.quantity)}</TableCell>
                      <TableCell className="text-right font-medium">{formatBRL(position.marketValue)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-col items-end">
                          <span className={position.unrealizedPnl >= 0 ? "text-positive" : "text-negative"}>
                            {formatBRLSigned(position.unrealizedPnl)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {formatPercent(position.unrealizedPnlPct)}
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Movimentações recentes</CardTitle>
            <CardDescription>{meta.operationsDescription}</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {recentOperations.length === 0 ? (
              <EmptyState title="Sem movimentações detalhadas" description={meta.operationsDescription} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                    <TableHead>Ativo</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentOperations.map((operation) => (
                    <TableRow key={`${operation.portfolioId}-${operation.id}`}>
                      <TableCell>{formatDate(operation.date)}</TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <Badge variant="outline">{operation.portfolioName}</Badge>
                        </TableCell>
                      ) : null}
                      <TableCell className="font-medium">{operation.assetCode}</TableCell>
                      <TableCell>
                        <Badge variant="muted">{operation.type}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-medium">{formatBRL(operation.total)}</TableCell>
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

export function ClassFamilyPositionsPage({ classFamily }: { classFamily: ClassFamily }) {
  const meta = FAMILY_META[classFamily];
  const {
    scope,
    activePortfolio,
    isLoading,
    error,
    positions,
  } = useClassFamilyData(classFamily);

  if (isLoading) {
    return renderState(meta.title, "Carregando posições da classe...", "Posições");
  }

  if (error) {
    return renderState(meta.title, "Falha ao carregar posições. Verifique se a API está rodando.", "Posições");
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return renderState(meta.title, "Selecione uma carteira válida na navegação lateral.", "Posições");
  }

  const title = scope.isGlobalScope
    ? `Posições - ${meta.title.toLowerCase()}`
    : `Posições - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? `Posições consolidadas de ${meta.title.toLowerCase()} em todas as carteiras.`
    : `Posições da classe ${meta.title.toLowerCase()} na carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Posições" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Ativos da classe</CardTitle>
            <CardDescription>{positions.length} ativo{positions.length === 1 ? "" : "s"} encontrados</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {positions.length === 0 ? (
              <EmptyState title={meta.emptyTitle} description={meta.emptyDescription} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ativo</TableHead>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                    <TableHead className="text-right">Qtd.</TableHead>
                    <TableHead className="text-right">Preço médio</TableHead>
                    <TableHead className="text-right">Cotação</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                    <TableHead className="text-right">Resultado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((position) => (
                    <TableRow key={`${position.portfolioId}-${position.assetCode}-${position.name}`}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">{position.assetCode}</span>
                          <span className="text-xs text-muted-foreground">{position.name}</span>
                        </div>
                      </TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <Badge variant="outline">{position.portfolioName}</Badge>
                        </TableCell>
                      ) : null}
                      <TableCell className="text-right">{formatQuantity(position.quantity)}</TableCell>
                      <TableCell className="text-right">{formatBRL(position.avgPrice)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span>{formatBRL(position.marketPrice)}</span>
                          <Badge variant={quoteStatusVariant[position.quoteStatus] ?? "outline"}>
                            {quoteStatusLabel[position.quoteStatus] ?? position.quoteStatus}
                          </Badge>
                          {position.quoteStatus !== "avg_fallback" ? (
                            <span className="text-[11px] text-muted-foreground">
                              {position.quoteSource}
                              {formatQuoteAge(position.quoteAgeSeconds)
                                ? ` · há ${formatQuoteAge(position.quoteAgeSeconds)}`
                                : ""}
                            </span>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-medium">{formatBRL(position.marketValue)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-col items-end">
                          <span className={position.unrealizedPnl >= 0 ? "text-positive" : "text-negative"}>
                            {formatBRLSigned(position.unrealizedPnl)}
                          </span>
                          <span className="text-xs text-muted-foreground">{formatPercent(position.unrealizedPnlPct)}</span>
                        </div>
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

export function ClassFamilyOperationsPage({ classFamily }: { classFamily: ClassFamily }) {
  const meta = FAMILY_META[classFamily];
  const {
    scope,
    activePortfolio,
    isLoading,
    error,
    operations,
  } = useClassFamilyData(classFamily);

  if (isLoading) {
    return renderState(meta.title, "Carregando operações da classe...", "Operações");
  }

  if (error) {
    return renderState(meta.title, "Falha ao carregar operações. Verifique se a API está rodando.", "Operações");
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return renderState(meta.title, "Selecione uma carteira válida na navegação lateral.", "Operações");
  }

  const title = scope.isGlobalScope
    ? `Operações - ${meta.title.toLowerCase()}`
    : `Operações - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? meta.operationsDescription
    : `${meta.operationsDescription} Carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Operações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Eventos da classe</CardTitle>
            <CardDescription>{meta.operationsDescription}</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            {operations.length === 0 ? (
              <EmptyState title="Sem movimentações detalhadas" description={meta.operationsDescription} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                    <TableHead>Ativo</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Qtd.</TableHead>
                    <TableHead className="text-right">Preço unit.</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {operations.map((operation) => (
                    <TableRow key={`${operation.portfolioId}-${operation.id}`}>
                      <TableCell>{formatDate(operation.date)}</TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <Badge variant="outline">{operation.portfolioName}</Badge>
                        </TableCell>
                      ) : null}
                      <TableCell className="font-medium">{operation.assetCode}</TableCell>
                      <TableCell>
                        <Badge variant="muted">{operation.type}</Badge>
                      </TableCell>
                      <TableCell className="text-right">{formatQuantity(operation.quantity)}</TableCell>
                      <TableCell className="text-right">{formatBRL(operation.unitPrice)}</TableCell>
                      <TableCell className="text-right font-medium">{formatBRL(operation.total)}</TableCell>
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
