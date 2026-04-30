"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
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
import { OwnerPortfolioBadge } from "@/components/portfolio/owner-portfolio-badge";
import {
  formatBRL,
  formatBRLCompact,
  formatBRLSigned,
  formatPercent,
  formatQuantity,
} from "@/lib/money";
import { usePrevidenciaHistory } from "@/lib/queries";
import type { PrevidenciaHistorySnapshot } from "@/lib/api";
import type { Portfolio } from "@/types/domain";

type RangeKey = "12m" | "24m" | "60m" | "ytd" | "all";
type Metric = "value" | "quantity" | "unitPrice";

const RANGE_LABELS: Record<RangeKey, string> = {
  "12m": "12m",
  "24m": "24m",
  "60m": "5a",
  ytd: "YTD",
  all: "Máx",
};

const METRIC_META: Record<
  Metric,
  { label: string; format: (v: number) => string; tickFormat: (v: number) => string }
> = {
  value: {
    label: "Valor de mercado",
    format: (v) => formatBRL(v),
    tickFormat: (v) => formatBRLCompact(v),
  },
  quantity: {
    label: "Cotas",
    format: (v) => formatQuantity(v),
    tickFormat: (v) => formatQuantity(v),
  },
  unitPrice: {
    label: "Preço da cota",
    format: (v) => formatBRL(v),
    tickFormat: (v) => formatBRLCompact(v),
  },
};

function formatMonthPt(month: string): string {
  const [y, m] = month.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, 1));
  return dt
    .toLocaleDateString("pt-BR", {
      month: "short",
      year: "2-digit",
      timeZone: "UTC",
    })
    .replace(".", "");
}

function filterByRange(
  snapshots: PrevidenciaHistorySnapshot[],
  range: RangeKey,
): PrevidenciaHistorySnapshot[] {
  if (range === "all" || snapshots.length === 0) return snapshots;
  if (range === "ytd") {
    const last = snapshots[snapshots.length - 1];
    const year = last.periodMonth.slice(0, 4);
    return snapshots.filter((s) => s.periodMonth.startsWith(year));
  }
  const cap = range === "12m" ? 12 : range === "24m" ? 24 : 60;
  return snapshots.slice(Math.max(0, snapshots.length - cap));
}

interface AssetGroup {
  assetCode: string;
  productName: string;
  snapshots: PrevidenciaHistorySnapshot[];
}

function groupByAsset(snapshots: PrevidenciaHistorySnapshot[]): AssetGroup[] {
  const map = new Map<string, AssetGroup>();
  for (const snap of snapshots) {
    const existing = map.get(snap.assetCode);
    if (existing) {
      existing.snapshots.push(snap);
    } else {
      map.set(snap.assetCode, {
        assetCode: snap.assetCode,
        productName: snap.productName,
        snapshots: [snap],
      });
    }
  }
  return Array.from(map.values());
}

interface AssetHistoryBlockProps {
  group: AssetGroup;
}

function AssetHistoryBlock({ group }: AssetHistoryBlockProps) {
  const [range, setRange] = useState<RangeKey>("24m");
  const [metric, setMetric] = useState<Metric>("value");
  const [showTable, setShowTable] = useState(false);

  const filtered = useMemo(
    () => filterByRange(group.snapshots, range),
    [group.snapshots, range],
  );

  const rows = useMemo(
    () =>
      filtered.map((s) => ({
        month: s.periodMonth,
        value: s.marketValueCents,
        quantity: s.quantity,
        unitPrice: s.unitPriceCents,
      })),
    [filtered],
  );

  const first = group.snapshots[0];
  const last = group.snapshots[group.snapshots.length - 1];
  const totalReturnPct =
    first && last && first.marketValueCents > 0
      ? (last.marketValueCents - first.marketValueCents) / first.marketValueCents
      : 0;
  const valueDelta = last && first ? last.marketValueCents - first.marketValueCents : 0;
  const meta = METRIC_META[metric];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-md border bg-card p-3">
          <p className="text-xs text-muted-foreground">Valor atual</p>
          <p className="mt-1 text-lg font-semibold">
            {last ? formatBRL(last.marketValueCents) : "—"}
          </p>
          {last && (
            <p className="text-xs text-muted-foreground">
              {formatMonthPt(last.periodMonth)}
            </p>
          )}
        </div>
        <div className="rounded-md border bg-card p-3">
          <p className="text-xs text-muted-foreground">Cotas atuais</p>
          <p className="mt-1 text-lg font-semibold">
            {last ? formatQuantity(last.quantity) : "—"}
          </p>
          {last && (
            <p className="text-xs text-muted-foreground">
              {formatBRL(last.unitPriceCents)} / cota
            </p>
          )}
        </div>
        <div className="rounded-md border bg-card p-3">
          <p className="text-xs text-muted-foreground">Variação no histórico</p>
          <p className="mt-1 text-lg font-semibold">
            {formatBRLSigned(valueDelta)}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatPercent(totalReturnPct)} desde {first ? formatMonthPt(first.periodMonth) : "—"}
          </p>
        </div>
        <div className="rounded-md border bg-card p-3">
          <p className="text-xs text-muted-foreground">Período coberto</p>
          <p className="mt-1 text-lg font-semibold">
            {first && last
              ? `${formatMonthPt(first.periodMonth)} → ${formatMonthPt(last.periodMonth)}`
              : "—"}
          </p>
          <p className="text-xs text-muted-foreground">
            {group.snapshots.length} extratos mensais
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-md border bg-card text-xs">
          {(Object.keys(METRIC_META) as Metric[]).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setMetric(opt)}
              className={`px-3 py-1.5 transition ${
                metric === opt
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
            >
              {METRIC_META[opt].label}
            </button>
          ))}
        </div>
        <div className="inline-flex rounded-md border bg-card text-xs">
          {(Object.keys(RANGE_LABELS) as RangeKey[]).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setRange(opt)}
              className={`px-3 py-1.5 transition ${
                range === opt
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
            >
              {RANGE_LABELS[opt]}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[300px] w-full">
        {rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Sem dados no período.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="month"
                tickFormatter={formatMonthPt}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => meta.tickFormat(Number(v) || 0)}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
                width={70}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(label) => formatMonthPt(String(label))}
                formatter={(value) => [meta.format(Number(value) || 0), meta.label]}
              />
              <Line
                type="monotone"
                dataKey={metric}
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="text-xs font-medium text-primary hover:underline"
        >
          {showTable ? "Ocultar" : "Ver"} histórico completo ({group.snapshots.length} meses)
        </button>
        {showTable && (
          <div className="mt-3 max-h-[420px] overflow-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Mês</TableHead>
                  <TableHead className="text-right">Cotas</TableHead>
                  <TableHead className="text-right">Preço da cota</TableHead>
                  <TableHead className="text-right">Valor de mercado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...group.snapshots].reverse().map((snap) => (
                  <TableRow key={`${snap.assetCode}-${snap.periodMonth}-${snap.id ?? ""}`}>
                    <TableCell className="font-medium">
                      {formatMonthPt(snap.periodMonth)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatQuantity(snap.quantity)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatBRL(snap.unitPriceCents)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatBRL(snap.marketValueCents)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}

export interface PrevidenciaHistorySectionProps {
  portfolio: Portfolio;
}

export function PrevidenciaHistorySection({ portfolio }: PrevidenciaHistorySectionProps) {
  const { data, isLoading, isError } = usePrevidenciaHistory(portfolio.id);

  const groups = useMemo(
    () => (data ? groupByAsset(data.snapshots) : []),
    [data],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              {portfolio.name}
              <OwnerPortfolioBadge
                portfolioName={portfolio.name}
                ownerName={portfolio.owner?.displayName ?? portfolio.owner?.name}
              />
            </CardTitle>
            <CardDescription>
              Evolução mensal de cotas, preço unitário e valor de mercado.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando histórico...</p>
        ) : isError ? (
          <p className="text-sm text-destructive">Falha ao carregar histórico.</p>
        ) : groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum snapshot histórico disponível para esta carteira.
          </p>
        ) : (
          <div className="space-y-8">
            {groups.map((group) => (
              <div key={group.assetCode} className="space-y-3">
                {groups.length > 1 && (
                  <h4 className="text-sm font-semibold">
                    {group.productName}{" "}
                    <span className="font-normal text-muted-foreground">
                      ({group.assetCode})
                    </span>
                  </h4>
                )}
                <AssetHistoryBlock group={group} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
