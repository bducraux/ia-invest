"use client";

import { TopBar } from "@/components/layout/topbar";
import { EmptyState, PageHeader } from "@/components/layout/page-header";
import { PrevidenciaHistorySection } from "@/features/previdencia/previdencia-history-section";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";

export default function PrevidenciaPage() {
  const scope = useDashboardScope();
  const { data: portfolios, isLoading } = usePortfolios();

  const allPrevidencia =
    portfolios?.filter((p) => p.specialization === "PREVIDENCIA") ?? [];
  const visible = scope.isGlobalScope
    ? allPrevidencia
    : allPrevidencia.filter((p) => p.id === scope.portfolioId);

  const title = scope.isGlobalScope
    ? "Previdência consolidada"
    : visible[0]?.name
      ? `Previdência - ${visible[0].name}`
      : "Previdência";
  const description =
    "Histórico mensal de cotas, preço unitário e valor de mercado dos planos PGBL/VGBL.";

  return (
    <>
      <TopBar title="Previdência" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader title={title} description={description} />

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando carteiras...</p>
        ) : visible.length === 0 ? (
          <EmptyState
            title="Nenhuma carteira de previdência"
            description="Importe extratos de previdência para consolidar esta visão."
          />
        ) : (
          visible.map((portfolio) => (
            <PrevidenciaHistorySection key={portfolio.id} portfolio={portfolio} />
          ))
        )}
      </main>
    </>
  );
}
