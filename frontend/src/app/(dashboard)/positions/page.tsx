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
import {
  formatBRL,
  formatBRLSigned,
  formatPercent,
  formatQuantity,
} from "@/lib/money";
import { usePortfolioPositions, usePortfolios } from "@/lib/queries";

const classLabels: Record<string, string> = {
  ACAO: "Ação",
  FII: "FII",
  ETF: "ETF",
  RENDA_FIXA: "Renda Fixa",
  CAIXA: "Caixa",
  CRIPTO: "Cripto",
};

export default function PositionsPage() {
  const portfoliosQuery = usePortfolios();
  const activePortfolio = portfoliosQuery.data?.[0];
  const positionsQuery = usePortfolioPositions(activePortfolio?.id, true);

  if (portfoliosQuery.isLoading || positionsQuery.isLoading) {
    return (
      <>
        <TopBar title="Posições" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Posições atuais" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (portfoliosQuery.error || positionsQuery.error) {
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

  const positions = positionsQuery.data ?? [];

  return (
    <>
      <TopBar title="Posições" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Posições atuais"
          description="Ativos consolidados a partir das suas operações."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Carteira</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ativo</TableHead>
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
                  <TableRow key={p.assetCode}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">{p.assetCode}</span>
                        <span className="text-xs text-muted-foreground">{p.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="muted">{classLabels[p.assetClass] ?? p.assetClass}</Badge>
                    </TableCell>
                    <TableCell className="text-right">{formatQuantity(p.quantity)}</TableCell>
                    <TableCell className="text-right">{formatBRL(p.avgPrice)}</TableCell>
                    <TableCell className="text-right">{formatBRL(p.marketPrice)}</TableCell>
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
