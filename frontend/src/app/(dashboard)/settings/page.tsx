"use client";

import { useMemo, useState } from "react";
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
  getAppSettings,
  updateAppSettings,
  calculateDailyRateFromAnnual,
  updatePortfolioName,
} from "@/lib/api";
import { usePortfolios } from "@/lib/queries";

export default function SettingsPage() {
  const portfoliosQuery = usePortfolios();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["app-settings"],
    queryFn: getAppSettings,
  });
  const [draftRates, setDraftRates] = useState<{
    cdi: string;
    selic: string;
    ipca: string;
  } | null>(null);
  const [draftPortfolioNames, setDraftPortfolioNames] = useState<Record<string, string>>({});

  const baseRates = useMemo(() => {
    const data = settingsQuery.data;
    return {
      cdi: data?.cdiAnnualRate === null || data?.cdiAnnualRate === undefined
        ? ""
        : String(data.cdiAnnualRate),
      selic: data?.selicAnnualRate === null || data?.selicAnnualRate === undefined
        ? ""
        : String(data.selicAnnualRate),
      ipca: data?.ipcaAnnualRate === null || data?.ipcaAnnualRate === undefined
        ? ""
        : String(data.ipcaAnnualRate),
    };
  }, [settingsQuery.data]);

  const cdiInput = draftRates?.cdi ?? baseRates.cdi;
  const selicInput = draftRates?.selic ?? baseRates.selic;
  const ipcaInput = draftRates?.ipca ?? baseRates.ipca;

  function setRateInput(field: "cdi" | "selic" | "ipca", value: string) {
    setDraftRates((prev) => ({
      cdi: prev?.cdi ?? baseRates.cdi,
      selic: prev?.selic ?? baseRates.selic,
      ipca: prev?.ipca ?? baseRates.ipca,
      [field]: value,
    }));
  }

  const saveSettingsMutation = useMutation({
    mutationFn: () => {
      return updateAppSettings({
        cdiAnnualRate: cdiInput.trim() === "" ? null : Number(cdiInput.trim()),
        selicAnnualRate: selicInput.trim() === "" ? null : Number(selicInput.trim()),
        ipcaAnnualRate: ipcaInput.trim() === "" ? null : Number(ipcaInput.trim()),
      });
    },
    onSuccess: () => {
      setDraftRates(null);
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      queryClient.invalidateQueries({ queryKey: ["fixed-income"] });
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
                  </div>
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
            <CardTitle className="text-base text-foreground">Taxas de Referência</CardTitle>
            <CardDescription>
              Informe as taxas anuais em <strong>porcentagem</strong> (ex: 14.65 para 14,65% a.a.).
              O sistema converte automaticamente para taxas diárias usando 252 dias úteis.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* CDI */}
            <div className="space-y-2">
              <label htmlFor="cdiAnnualRate" className="text-sm font-medium">
                CDI anual (%)
              </label>
              <Input
                id="cdiAnnualRate"
                type="number"
                step="0.01"
                placeholder="Ex.: 14.65"
                value={cdiInput}
                onChange={(event) => setRateInput("cdi", event.target.value)}
              />
              {cdiInput.trim() && !isNaN(Number(cdiInput)) && Number(cdiInput) > 0 && (
                <p className="text-xs text-muted-foreground">
                  Equivale a {(calculateDailyRateFromAnnual(Number(cdiInput)) * 100).toFixed(4)}% ao dia útil (base 252 d.u.)
                </p>
              )}
            </div>

            {/* SELIC */}
            <div className="space-y-2">
              <label htmlFor="selicAnnualRate" className="text-sm font-medium">
                SELIC anual (%)
              </label>
              <Input
                id="selicAnnualRate"
                type="number"
                step="0.01"
                placeholder="Ex.: 14.65"
                value={selicInput}
                onChange={(event) => setRateInput("selic", event.target.value)}
              />
              {selicInput.trim() && !isNaN(Number(selicInput)) && Number(selicInput) > 0 && (
                <p className="text-xs text-muted-foreground">
                  Equivale a {(calculateDailyRateFromAnnual(Number(selicInput)) * 100).toFixed(4)}% ao dia útil (base 252 d.u.)
                </p>
              )}
            </div>

            {/* IPCA */}
            <div className="space-y-2">
              <label htmlFor="ipcaAnnualRate" className="text-sm font-medium">
                IPCA anual (%)
              </label>
              <Input
                id="ipcaAnnualRate"
                type="number"
                step="0.01"
                placeholder="Ex.: 4.14"
                value={ipcaInput}
                onChange={(event) => setRateInput("ipca", event.target.value)}
              />
              {ipcaInput.trim() && !isNaN(Number(ipcaInput)) && Number(ipcaInput) > 0 && (
                <p className="text-xs text-muted-foreground">
                  Equivale a {(calculateDailyRateFromAnnual(Number(ipcaInput)) * 100).toFixed(4)}% ao dia útil (base 252 d.u.)
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <Button
                onClick={() => saveSettingsMutation.mutate()}
                disabled={saveSettingsMutation.isPending || settingsQuery.isLoading}
              >
                Salvar Taxas
              </Button>
              {saveSettingsMutation.isSuccess && (
                <span className="text-xs text-emerald-600">Configuração salva.</span>
              )}
              {saveSettingsMutation.error instanceof Error && (
                <span className="text-xs text-destructive">
                  {saveSettingsMutation.error.message}
                </span>
              )}
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
