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
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard } from "@/features/dashboard/kpi-card";
import { AllocationDonut } from "@/features/dashboard/allocation-donut";
import { PerformanceChart } from "@/features/dashboard/performance-chart";
import {
  formatBRL,
  formatBRLSigned,
  formatPercent,
} from "@/lib/money";
import { formatDate } from "@/lib/date";
import {
  mockOperations,
  mockSummary,
} from "@/mocks/data";
import {
  Banknote,
  Coins,
  TrendingUp,
  Wallet,
} from "lucide-react";

export default function OverviewPage() {
  const summary = mockSummary;
  const recent = mockOperations.slice(0, 6);

  return (
    <>
      <TopBar title="Visão geral" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Sua carteira"
          description="Resumo consolidado em tempo real, com dados locais."
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            title="Patrimônio atual"
            value={formatBRL(summary.marketValue)}
            subValue={`Caixa: ${formatBRL(summary.cashBalance)}`}
            icon={<Wallet className="h-4 w-4" />}
          />
          <KpiCard
            title="Total investido"
            value={formatBRL(summary.totalInvested)}
            subValue="Custo médio agregado"
            icon={<Banknote className="h-4 w-4" />}
          />
          <KpiCard
            title="Resultado (não realizado)"
            value={formatBRLSigned(summary.unrealizedPnl)}
            trend={{
              label: formatPercent(summary.unrealizedPnlPct),
              positive: summary.unrealizedPnl >= 0,
            }}
            icon={<TrendingUp className="h-4 w-4" />}
          />
          <KpiCard
            title="Proventos no mês"
            value={formatBRL(summary.monthDividends)}
            trend={{
              label: formatPercent(summary.ytdReturnPct),
              positive: summary.ytdReturnPct >= 0,
            }}
            subValue="Retorno YTD"
            icon={<Coins className="h-4 w-4" />}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base text-foreground">
                Evolução do patrimônio
              </CardTitle>
              <CardDescription>Últimos 12 meses</CardDescription>
            </CardHeader>
            <CardContent>
              <PerformanceChart data={summary.performance} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base text-foreground">
                Alocação por classe
              </CardTitle>
              <CardDescription>Distribuição atual</CardDescription>
            </CardHeader>
            <CardContent>
              <AllocationDonut data={summary.allocation} />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base text-foreground">
                Operações recentes
              </CardTitle>
              <CardDescription>Últimos lançamentos importados</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  <TableHead className="text-right">Preço</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((op) => (
                  <TableRow key={op.id}>
                    <TableCell>{formatDate(op.date)}</TableCell>
                    <TableCell className="font-medium">{op.assetCode}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          op.type === "COMPRA"
                            ? "positive"
                            : op.type === "VENDA"
                              ? "negative"
                              : "muted"
                        }
                      >
                        {op.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{op.quantity}</TableCell>
                    <TableCell className="text-right">
                      {formatBRL(op.unitPrice)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatBRL(op.total)}
                    </TableCell>
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
