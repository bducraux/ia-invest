"use client";

import Link from "next/link";
import { use } from "react";
import { ArrowLeft, Briefcase } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { OwnerBadge } from "@/components/members/owner-badge";
import { useMember, useMemberPortfolios, useMemberSummary } from "@/lib/queries";
import { formatBRLSigned, type Cents, formatBRL } from "@/lib/money";

export default function MemberDetailPage({
  params,
}: {
  params: Promise<{ memberId: string }>;
}) {
  const { memberId } = use(params);
  const memberQuery = useMember(memberId);
  const portfoliosQuery = useMemberPortfolios(memberId);
  const summaryQuery = useMemberSummary(memberId);

  const member = memberQuery.data;
  const portfolios = portfoliosQuery.data ?? [];
  const summary = summaryQuery.data;

  return (
    <main className="flex-1 space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/members"
            className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Membros
          </Link>
          <h1 className="text-2xl font-semibold">
            {member?.displayName || member?.name || memberId}
          </h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <OwnerBadge owner={member ?? null} />
            {member?.email ? <span>{member.email}</span> : null}
          </div>
        </div>
      </header>

      {summary ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Carteiras
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold tabular-nums">
              {summary.portfolios.length}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Posições abertas
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold tabular-nums">
              {summary.totals.open_positions}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Custo total
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold tabular-nums">
              {formatBRL(summary.totals.total_cost_cents as Cents)}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                P/L realizado
              </CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold tabular-nums">
              {formatBRLSigned(summary.totals.realized_pnl_cents as Cents)}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Briefcase className="h-4 w-4" /> Carteiras
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Carteira</TableHead>
                <TableHead>Especialização</TableHead>
                <TableHead className="text-right">Posições</TableHead>
                <TableHead className="text-right">Custo</TableHead>
                <TableHead className="text-right">P/L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {portfolios.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    Sem carteiras associadas a este membro.
                  </TableCell>
                </TableRow>
              ) : (
                portfolios.map((portfolio) => {
                  const summaryRow = summary?.portfolios.find(
                    (p) => p.id === portfolio.id,
                  );
                  return (
                    <TableRow key={portfolio.id}>
                      <TableCell>
                        <Link
                          href={`/portfolio/${portfolio.id}`}
                          className="font-medium hover:underline"
                        >
                          {portfolio.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {portfolio.specialization}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {summaryRow?.open_positions ?? 0}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatBRL((summaryRow?.total_cost_cents ?? 0) as Cents)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatBRLSigned(
                          (summaryRow?.realized_pnl_cents ?? 0) as Cents,
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
