"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatBRL, formatBRLCompact } from "@/lib/money";
import type { EquityCurve } from "@/types/domain";

type RangeKey = "12m" | "24m" | "ytd" | "all";

interface RowDatum {
  month: string;
  total: number;
  contributions: number;
}

const PATRIMONIO_COLOR = "#1f3a8a"; // dark blue
const INVESTIDO_COLOR = "#22b8cf"; // cyan

function filterByRange(months: EquityCurve["series"], range: RangeKey) {
  if (range === "all" || months.length === 0) return months;
  if (range === "ytd") {
    const last = months[months.length - 1];
    const year = last.month.slice(0, 4);
    return months.filter((p) => p.month.startsWith(year));
  }
  const cap = range === "12m" ? 12 : 24;
  return months.slice(Math.max(0, months.length - cap));
}

function formatMonthPt(month: string): string {
  const [y, m] = month.split("-").map((s) => Number(s));
  const dt = new Date(Date.UTC(y, m - 1, 1));
  return dt
    .toLocaleDateString("pt-BR", {
      month: "short",
      year: "2-digit",
      timeZone: "UTC",
    })
    .replace(".", "");
}

export interface EquityCurveChartProps {
  data: EquityCurve | undefined;
  isLoading?: boolean;
  defaultRange?: RangeKey;
}

export function EquityCurveChart({
  data,
  isLoading = false,
  defaultRange = "12m",
}: EquityCurveChartProps) {
  const [range, setRange] = useState<RangeKey>(defaultRange);

  const filtered = useMemo(
    () => filterByRange(data?.series ?? [], range),
    [data?.series, range],
  );

  const rows: RowDatum[] = useMemo(
    () =>
      filtered.map((p) => ({
        month: p.month,
        total: p.marketValue,
        contributions: p.cumulativeContributions,
      })),
    [filtered],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-muted-foreground">
          Evolução patrimonial
        </h3>
        <div className="inline-flex rounded-md border bg-card text-xs">
          {(["12m", "24m", "ytd", "all"] as RangeKey[]).map((opt) => (
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
              {opt === "12m" && "12m"}
              {opt === "24m" && "24m"}
              {opt === "ytd" && "YTD"}
              {opt === "all" && "Máx"}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[320px] w-full">
        {isLoading || rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {isLoading ? "Carregando série histórica..." : "Sem dados no período."}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={PATRIMONIO_COLOR} stopOpacity={0.18} />
                  <stop offset="100%" stopColor={PATRIMONIO_COLOR} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="month"
                tickFormatter={formatMonthPt}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                tickFormatter={(v) => formatBRLCompact(Number(v) || 0)}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
                width={70}
              />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(label) => formatMonthPt(String(label))}
                formatter={(value, name) => {
                  const label =
                    name === "total"
                      ? "Patrimônio"
                      : name === "contributions"
                        ? "Valor investido"
                        : String(name);
                  return [formatBRL(Number(value) || 0), label];
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                iconType="plainline"
                formatter={(value) => {
                  if (value === "total") return "Patrimônio";
                  if (value === "contributions") return "Valor investido";
                  return value;
                }}
              />
              <Area
                type="monotone"
                dataKey="total"
                stroke={PATRIMONIO_COLOR}
                strokeWidth={2}
                fill="url(#equityFill)"
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="contributions"
                stroke={INVESTIDO_COLOR}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
