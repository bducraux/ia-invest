"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { usePortfolios } from "@/lib/queries";

export default function SettingsPage() {
  const portfoliosQuery = usePortfolios();

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
              Carteiras configuradas no banco SQLite local.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {portfolios.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md border border-border px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">{p.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {p.id} · {p.currency}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">SQLite local</span>
              </div>
            ))}
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
