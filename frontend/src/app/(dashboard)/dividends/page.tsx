import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { DividendsBarChart } from "@/features/dividends/dividends-bar-chart";
import { formatBRL } from "@/lib/money";
import { formatDate } from "@/lib/date";
import { mockDividends, mockDividendsByMonth } from "@/mocks/data";

export default function DividendsPage() {
  const total = mockDividendsByMonth.reduce((acc, m) => acc + m.amount, 0);

  return (
    <>
      <TopBar title="Proventos" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Proventos recebidos"
          description="Dividendos e juros sobre capital próprio dos últimos meses."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">
              Histórico mensal
            </CardTitle>
            <CardDescription>
              Total no período: <strong className="text-foreground">{formatBRL(total)}</strong>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DividendsBarChart data={mockDividendsByMonth} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Lançamentos</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockDividends.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>{formatDate(d.date)}</TableCell>
                    <TableCell className="font-medium">{d.assetCode}</TableCell>
                    <TableCell>
                      <Badge variant="muted">{d.type}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium text-positive">
                      {formatBRL(d.amount)}
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
