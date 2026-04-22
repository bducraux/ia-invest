"use client";

import { useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader, EmptyState } from "@/components/layout/page-header";
import { Upload } from "lucide-react";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";

function buildInboxPath(portfolioId: string): string {
  return `portfolios/${portfolioId}/inbox`;
}

export default function ImportPage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = useMemo(() => portfoliosQuery.data ?? [], [portfoliosQuery.data]);
  const [preferredPortfolioId, setPreferredPortfolioId] = useState<string>("");

  const selectedPortfolioId = portfolios.some((p) => p.id === preferredPortfolioId)
    ? preferredPortfolioId
    : portfolios.some((p) => p.id === scope.portfolioId)
      ? (scope.portfolioId as string)
      : portfolios[0]?.id ?? "";
  const selectedPortfolio = portfolios.find((p) => p.id === selectedPortfolioId);

  return (
    <>
      <TopBar title="Importar" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Importar operações"
          description="Importação é feita por carteira. Selecione a carteira de destino para definir a pasta inbox correta."
          actions={
            portfolios.length > 0 ? (
              <label className="flex min-w-64 flex-col gap-1 text-xs text-muted-foreground">
                Carteira de destino
                <select
                  className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                  value={selectedPortfolioId}
                  onChange={(event) => setPreferredPortfolioId(event.target.value)}
                >
                  {portfolios.map((portfolio) => (
                    <option key={portfolio.id} value={portfolio.id}>
                      {portfolio.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null
          }
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Formatos por carteira</CardTitle>
            <CardDescription>
              Os formatos aceitos variam por carteira, de acordo com o arquivo <code>portfolio.yml</code>.
              Exemplos já usados neste projeto: <code>b3_csv</code>, <code>broker_csv</code>, <code>fixed_income_csv</code>, <code>binance_csv</code> e <code>previdencia_ibm_pdf</code>.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {selectedPortfolio ? (
              <div className="mb-4 rounded-md border border-border bg-muted/30 px-4 py-3 text-sm">
                <p className="font-medium text-foreground">Destino atual da importação</p>
                <p className="text-muted-foreground">
                  Carteira: <span className="font-medium text-foreground">{selectedPortfolio.name}</span>
                </p>
                <p className="font-mono text-xs text-muted-foreground">
                  {buildInboxPath(selectedPortfolio.id)}
                </p>
              </div>
            ) : null}
            <EmptyState
              title="Arraste seus arquivos aqui"
              description="Ou clique para selecionar. Na integração com backend, os arquivos irão para a inbox da carteira selecionada."
            >
              <div className="mt-4 inline-flex items-center gap-2 rounded-md border border-dashed border-border px-4 py-2 text-sm text-muted-foreground">
                <Upload className="h-4 w-4" />
                Aguardando integração com o backend
              </div>
            </EmptyState>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
