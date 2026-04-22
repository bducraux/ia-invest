"use client";

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { Position } from "@/types/domain";
import { formatBRL, formatPercent } from "@/lib/money";

const COLORS = [
  "hsl(158 64% 52%)",
  "hsl(199 89% 60%)",
  "hsl(38 92% 60%)",
  "hsl(280 70% 65%)",
  "hsl(220 14% 60%)",
  "hsl(0 72% 60%)",
  "hsl(30 90% 60%)",
  "hsl(160 50% 45%)",
  "hsl(250 70% 65%)",
  "hsl(340 70% 60%)",
];

const MAX_SLICES = 9;

interface AssetSlice {
  label: string;
  value: number;
  weight: number;
}

export function AssetAllocationDonut({ positions }: { positions: Position[] }) {
  const open = positions.filter((p) => p.marketValue > 0);
  const total = open.reduce((sum, p) => sum + p.marketValue, 0);

  if (total === 0) {
    return (
      <div className="flex h-[260px] items-center justify-center text-sm text-muted-foreground">
        Sem posições abertas
      </div>
    );
  }

  const sorted = [...open].sort((a, b) => b.marketValue - a.marketValue);

  let slices: AssetSlice[];
  if (sorted.length <= MAX_SLICES) {
    slices = sorted.map((p) => ({
      label: p.assetCode,
      value: p.marketValue,
      weight: p.marketValue / total,
    }));
  } else {
    const top = sorted.slice(0, MAX_SLICES - 1);
    const rest = sorted.slice(MAX_SLICES - 1);
    const othersValue = rest.reduce((sum, p) => sum + p.marketValue, 0);
    slices = [
      ...top.map((p) => ({
        label: p.assetCode,
        value: p.marketValue,
        weight: p.marketValue / total,
      })),
      { label: "Outros", value: othersValue, weight: othersValue / total },
    ];
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={slices}
          dataKey="value"
          nameKey="label"
          innerRadius={60}
          outerRadius={95}
          paddingAngle={2}
          stroke="none"
        >
          {slices.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(value, _name, item) => {
            const slice = item.payload as AssetSlice;
            return [
              `${formatBRL(Number(value) || 0)} · ${formatPercent(slice.weight)}`,
              slice.label,
            ];
          }}
        />
        <Legend
          verticalAlign="bottom"
          height={36}
          wrapperStyle={{ fontSize: 12 }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
