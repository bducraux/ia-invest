"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import {
  updatePortfolioName,
  getBenchmarkCoverage,
  syncBenchmark,
  getFxCoverage,
  syncFx,
  exportPortfolio,
  type PortfolioExportResponse,
} from "@/lib/api";
import { usePortfolios } from "@/lib/queries";

export default function SettingsPage() {
  const portfoliosQuery = usePortfolios();
  const queryClient = useQueryClient();
  const [draftPortfolioNames, setDraftPortfolioNames] = useState<Record<string, string>>({});
  const [exportResults, setExportResults] = useState<Record<string, PortfolioExportResponse>>({});
  const [exportErrors, setExportErrors] = useState<Record<string, string>>({});

  const exportPortfolioMutation = useMutation({
    mutationFn: (portfolioId: string) => exportPortfolio(portfolioId),
    onSuccess: (data, portfolioId) => {
      setExportResults((prev) => ({ ...prev, [portfolioId]: data }));
      setExportErrors((prev) => {
        const next = { ...prev };
        delete next[portfolioId];
        return next;
      });
    },
    onError: (error, portfolioId) => {
      setExportErrors((prev) => ({
        ...prev,
        [portfolioId]: error instanceof Error ? error.message : "Falha ao exportar.",
      }));
    },
  });

  const renamePortfolioMutation = useMutation({
    mutationFn: ({ portfolioId, name }: { portfolioId: string; name: string }) =>
      updatePortfolioName(portfolioId, { name }),
    onSuccess: (_updatedPortfolio, variables) => {
      setDraftPortfolioNames((prev) => {
        const next = { ...prev };
        delete next[variables.portfolioId];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });

  const cdiCoverageQuery = useQuery({
    queryKey: ["benchmark-coverage", "CDI"],
    queryFn: () => getBenchmarkCoverage("CDI"),
  });

  const syncCdiMutation = useMutation({
    mutationFn: (fullRefresh: boolean) => syncBenchmark("CDI", { fullRefresh }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["benchmark-coverage", "CDI"] });
      queryClient.invalidateQueries({ queryKey: ["fixed-income"] });
    },
  });

  const usdbrlCoverageQuery = useQuery({
    queryKey: ["fx-coverage", "USDBRL"],
    queryFn: () => getFxCoverage("USDBRL"),
  });

  const syncUsdbrlMutation = useMutation({
    mutationFn: (fullRefresh: boolean) => syncFx("USDBRL", { fullRefresh }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fx-coverage", "USDBRL"] });
    },
  });

  if (portfoliosQuery.isLoading) {
    return (
      <>
        <TopBar title="Configurações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Configurações" description="Carregando carteiras..." />
        </main>
      </>
    );
  }

  if (portfoliosQuery.error) {
    return (
      <>
        <TopBar title="Configurações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Configurações"
            description="Falha ao carregar carteiras. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  const portfolios = portfoliosQuery.data ?? [];

  function getPortfolioNameDraft(portfolioId: string, portfolioName: string): string {
    return draftPortfolioNames[portfolioId] ?? portfolioName;
  }

  function setPortfolioNameDraft(portfolioId: string, value: string): void {
    setDraftPortfolioNames((prev) => ({
      ...prev,
      [portfolioId]: value,
    }));
  }

  return (
    <>
      <TopBar title="Configurações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Configurações"
          description="Preferências de exibição e gerenciamento de carteiras."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Carteiras</CardTitle>
            <CardDescription>
              Carteiras configuradas no banco SQLite local. Você pode renomear a carteira sem alterar o ID técnico.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {portfolios.map((p) => (
              <div
                key={p.id}
                className="flex flex-col gap-3 rounded-md border border-border px-4 py-3 md:flex-row md:items-center md:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    ID: {p.id} · {p.currency}
                  </p>
                  <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                    <Input
                      value={getPortfolioNameDraft(p.id, p.name)}
                      onChange={(event) => setPortfolioNameDraft(p.id, event.target.value)}
                      className="h-9 min-w-56"
                      aria-label={`Nome da carteira ${p.id}`}
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        renamePortfolioMutation.isPending
                        || getPortfolioNameDraft(p.id, p.name).trim() === ""
                        || getPortfolioNameDraft(p.id, p.name).trim() === p.name
                      }
                      onClick={() =>
                        renamePortfolioMutation.mutate({
                          portfolioId: p.id,
                          name: getPortfolioNameDraft(p.id, p.name).trim(),
                        })
                      }
                    >
                      Renomear
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        exportPortfolioMutation.isPending
                        && exportPortfolioMutation.variables === p.id
                      }
                      onClick={() => exportPortfolioMutation.mutate(p.id)}
                      title="Gera CSVs com todos os dados desta carteira em portfolios/<owner>/<slug>/exports/"
                    >
                      {exportPortfolioMutation.isPending && exportPortfolioMutation.variables === p.id
                        ? "Exportando..."
                        : "Exportar dados"}
                    </Button>
                  </div>
                  {exportResults[p.id] ? (
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {exportResults[p.id].totalFiles === 0 ? (
                        <p>Nenhum dado para exportar nesta carteira.</p>
                      ) : (
                        <>
                          <p className="text-emerald-600">
                            {exportResults[p.id].totalFiles} arquivo(s) gerado(s) em{" "}
                            <span className="font-mono">{exportResults[p.id].outputDir}</span>:
                          </p>
                          <ul className="list-disc pl-4">
                            {exportResults[p.id].files.map((file) => (
                              <li key={file.path} className="font-mono">
                                {file.path.split("/").slice(-1)[0]} ({file.rows} linha{file.rows === 1 ? "" : "s"})
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  ) : null}
                  {exportErrors[p.id] ? (
                    <p className="mt-2 text-xs text-destructive">{exportErrors[p.id]}</p>
                  ) : null}
                </div>
                <span className="text-xs text-muted-foreground">SQLite local</span>
              </div>
            ))}
            {renamePortfolioMutation.error instanceof Error ? (
              <p className="text-xs text-destructive">{renamePortfolioMutation.error.message}</p>
            ) : null}
            {renamePortfolioMutation.isSuccess ? (
              <p className="text-xs text-emerald-600">Nome da carteira atualizado.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Histórico CDI (BACEN)</CardTitle>
            <CardDescription>
              Série diária do CDI (SGS 12) sincronizada do Banco Central. Esta é
              a única fonte usada para valorização CDI_PERCENT.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {cdiCoverageQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">Carregando cobertura...</p>
            ) : cdiCoverageQuery.error instanceof Error ? (
              <p className="text-xs text-destructive">{cdiCoverageQuery.error.message}</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                <div>
                  <p className="text-xs text-muted-foreground">Início da cobertura</p>
                  <p className="font-medium">
                    {cdiCoverageQuery.data?.coverageStart ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Fim da cobertura</p>
                  <p className="font-medium">
                    {cdiCoverageQuery.data?.coverageEnd ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Dias úteis em cache</p>
                  <p className="font-medium">{cdiCoverageQuery.data?.rowCount ?? 0}</p>
                </div>
                {cdiCoverageQuery.data?.lastFetchedAt ? (
                  <div className="sm:col-span-3">
                    <p className="text-xs text-muted-foreground">
                      Última atualização: {cdiCoverageQuery.data.lastFetchedAt}
                    </p>
                  </div>
                ) : null}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={() => syncCdiMutation.mutate(false)}
                disabled={syncCdiMutation.isPending}
              >
                Sincronizar agora
              </Button>
              <Button
                variant="outline"
                onClick={() => syncCdiMutation.mutate(true)}
                disabled={syncCdiMutation.isPending}
              >
                Recarregar histórico completo
              </Button>
              {syncCdiMutation.isSuccess ? (
                <span className="text-xs text-emerald-600">
                  {syncCdiMutation.data.rowsInserted} dia(s) atualizado(s).
                </span>
              ) : null}
              {syncCdiMutation.error instanceof Error ? (
                <span className="text-xs text-destructive">
                  {syncCdiMutation.error.message}
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Histórico USDBRL PTAX (BACEN)</CardTitle>
            <CardDescription>
              Série diária da PTAX USD/BRL (venda) sincronizada do Banco Central.
              Usada para converter operações em dólar (Avenue/Apex) para BRL pela
              data de liquidação.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {usdbrlCoverageQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">Carregando cobertura...</p>
            ) : usdbrlCoverageQuery.error instanceof Error ? (
              <p className="text-xs text-destructive">{usdbrlCoverageQuery.error.message}</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                <div>
                  <p className="text-xs text-muted-foreground">Início da cobertura</p>
                  <p className="font-medium">
                    {usdbrlCoverageQuery.data?.coverageStart ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Fim da cobertura</p>
                  <p className="font-medium">
                    {usdbrlCoverageQuery.data?.coverageEnd ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Dias úteis em cache</p>
                  <p className="font-medium">{usdbrlCoverageQuery.data?.rowCount ?? 0}</p>
                </div>
                {usdbrlCoverageQuery.data?.lastFetchedAt ? (
                  <div className="sm:col-span-3">
                    <p className="text-xs text-muted-foreground">
                      Última atualização: {usdbrlCoverageQuery.data.lastFetchedAt}
                    </p>
                  </div>
                ) : null}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={() => syncUsdbrlMutation.mutate(false)}
                disabled={syncUsdbrlMutation.isPending}
              >
                Sincronizar agora
              </Button>
              <Button
                variant="outline"
                onClick={() => syncUsdbrlMutation.mutate(true)}
                disabled={syncUsdbrlMutation.isPending}
              >
                Recarregar histórico completo
              </Button>
              {syncUsdbrlMutation.isSuccess ? (
                <span className="text-xs text-emerald-600">
                  {syncUsdbrlMutation.data.rowsInserted} dia(s) atualizado(s).
                </span>
              ) : null}
              {syncUsdbrlMutation.error instanceof Error ? (
                <span className="text-xs text-destructive">
                  {syncUsdbrlMutation.error.message}
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Aparência</CardTitle>
            <CardDescription>
              Use o botão de tema na barra superior para alternar entre claro e escuro.
              O tema escuro é o padrão.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    </>
  );
}
