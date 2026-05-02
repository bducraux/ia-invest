"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Banknote,
  FileDown,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { useIrpfReport, usePortfolios } from "@/lib/queries";
import { IrpfSectionCard } from "@/components/irpf/irpf-section";

const CURRENT_YEAR = new Date().getFullYear();
// Gera últimos 6 anos (incluindo o anterior, default).
const YEAR_OPTIONS = Array.from({ length: 6 }, (_, i) => CURRENT_YEAR - 1 - i);

export function IrpfPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const activePortfolio = portfolios.find((p) => p.id === scope.portfolioId);

  const [year, setYear] = useState<number>(CURRENT_YEAR - 1);

  const reportQuery = useIrpfReport(scope.portfolioId, year);

  const isWrongType =
    activePortfolio && activePortfolio.specialization !== "RENDA_VARIAVEL";

  const sections = useMemo(
    () => reportQuery.data?.sections ?? [],
    [reportQuery.data],
  );
  const groupedSections = useMemo(() => {
    return {
      isento: sections.filter((s) => s.category === "isento"),
      exclusivo: sections.filter((s) => s.category === "exclusivo"),
      bens: sections.filter((s) => s.category === "bem_direito"),
    };
  }, [sections]);

  if (!scope.portfolioId) {
    return (
      <>
        <TopBar title="Simulador IR" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Simulador IR"
            description="Selecione uma carteira de Renda Variável na navegação lateral."
          />
        </main>
      </>
    );
  }

  if (isWrongType) {
    return (
      <>
        <TopBar title="Simulador IR" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Simulador IR"
            description={`A carteira "${activePortfolio.name}" não é do tipo Renda Variável.`}
          />
          <Card>
            <CardContent className="flex items-center gap-3 p-6 text-sm text-muted-foreground">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <span>
                O Simulador IR só está disponível para carteiras de Renda
                Variável (ações, FIIs, FIAGROs, BDRs e ETFs).
              </span>
            </CardContent>
          </Card>
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar title="Simulador IR" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title={`Simulador IR — ${activePortfolio?.name ?? "Carteira"}`}
          description="Projeção de DIRPF baseada nas operações e posições da carteira. Os valores aqui são gerados a partir do que está registrado no IA-Invest e devem ser conferidos antes de serem declarados."
        />

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>Ano-base</CardTitle>
              <p className="text-xs text-muted-foreground">
                Declaração entregue em {year + 1}, referente a {year}.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="irpf-year" className="text-xs text-muted-foreground">
                Ano-base
              </label>
              <select
                id="irpf-year"
                value={year}
                onChange={(event) => setYear(Number(event.target.value))}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                {YEAR_OPTIONS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
          </CardHeader>
        </Card>

        {reportQuery.isLoading ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Carregando dados do ano-base {year}...
            </CardContent>
          </Card>
        ) : reportQuery.error ? (
          <Card>
            <CardContent className="flex items-center gap-3 p-6 text-sm text-muted-foreground">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              <span>
                Falha ao carregar a projeção de IRPF. Verifique se a API está
                rodando.
              </span>
            </CardContent>
          </Card>
        ) : reportQuery.data ? (
          <>
            {reportQuery.data.warnings.length > 0 ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-amber-500">
                    <AlertTriangle className="h-4 w-4" />
                    Pontos de atenção
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {reportQuery.data.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ) : null}

            {sections.length === 0 ? (
              <Card>
                <CardContent className="flex items-center gap-3 p-6 text-sm text-muted-foreground">
                  <FileDown className="h-5 w-5" />
                  <span>
                    Nenhum lançamento encontrado para o ano-base {year}.
                  </span>
                </CardContent>
              </Card>
            ) : null}

            {groupedSections.isento.length > 0 ? (
              <section className="space-y-4">
                <h2 className="flex items-center gap-2 border-b border-border/60 pb-2 text-base font-bold text-foreground">
                  <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  Rendimentos Isentos e Não Tributáveis
                </h2>
                {groupedSections.isento.map((section) => (
                  <IrpfSectionCard key={section.code} section={section} />
                ))}
              </section>
            ) : null}

            {groupedSections.exclusivo.length > 0 ? (
              <section className="space-y-4">
                <h2 className="flex items-center gap-2 border-b border-border/60 pb-2 text-base font-bold text-foreground">
                  <ShieldAlert className="h-4 w-4 text-amber-500" />
                  Rendimentos Sujeitos à Tributação Exclusiva/Definitiva
                </h2>
                {groupedSections.exclusivo.map((section) => (
                  <IrpfSectionCard key={section.code} section={section} />
                ))}
              </section>
            ) : null}

            {groupedSections.bens.length > 0 ? (
              <section className="space-y-4">
                <h2 className="flex items-center gap-2 border-b border-border/60 pb-2 text-base font-bold text-foreground">
                  <Banknote className="h-4 w-4 text-emerald-500" />
                  Bens e Direitos
                </h2>
                {groupedSections.bens.map((section) => (
                  <IrpfSectionCard key={section.code} section={section} />
                ))}
              </section>
            ) : null}
          </>
        ) : null}
      </main>
    </>
  );
}
