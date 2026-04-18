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
import { formatBRL, formatQuantity } from "@/lib/money";
import { formatDate } from "@/lib/date";
import { usePortfolioOperations, usePortfolios } from "@/lib/queries";
import Link from "next/link";
import { Upload } from "lucide-react";

export default function OperationsPage() {
  const portfoliosQuery = usePortfolios();
  const activePortfolio = portfoliosQuery.data?.[0];
  const operationsQuery = usePortfolioOperations(activePortfolio?.id, {
    limit: 100,
    offset: 0,
  });

  if (portfoliosQuery.isLoading || operationsQuery.isLoading) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Histórico de operações" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (portfoliosQuery.error || operationsQuery.error) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Histórico de operações"
            description="Falha ao carregar operações. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  const operations = operationsQuery.data?.operations ?? [];
  const total = operationsQuery.data?.total ?? 0;

  return (
    <>
      <TopBar title="Operações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Histórico de operações"
          description="Compras, vendas e proventos importados das suas notas de corretagem."
          actions={
            <Link
              href="/import"
              className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-transparent px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <Upload className="h-4 w-4" />
              Importar
            </Link>
          }
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">
              {total} operações
            </CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  <TableHead className="text-right">Preço unit.</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Origem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {operations.map((op) => (
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
                    <TableCell className="text-right">{formatQuantity(op.quantity)}</TableCell>
                    <TableCell className="text-right">{formatBRL(op.unitPrice)}</TableCell>
                    <TableCell className="text-right font-medium">
                      {formatBRL(op.total)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{op.source}</TableCell>
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
