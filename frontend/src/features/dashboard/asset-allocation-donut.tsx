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
  "hsl(173 58% 45%)",
  "hsl(96 55% 55%)",
  "hsl(15 85% 62%)",
  "hsl(48 95% 55%)",
  "hsl(210 70% 55%)",
  "hsl(290 50% 55%)",
  "hsl(120 40% 50%)",
  "hsl(50 70% 50%)",
  "hsl(190 60% 50%)",
  "hsl(355 65% 55%)",
];

const MIN_WEIGHT_FOR_OWN_SLICE = 0.02;

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
  const allSlices: AssetSlice[] = sorted.map((p) => ({
    label: p.assetCode,
    value: p.marketValue,
    weight: p.marketValue / total,
  }));

  const major = allSlices.filter((s) => s.weight >= MIN_WEIGHT_FOR_OWN_SLICE);
  const minor = allSlices.filter((s) => s.weight < MIN_WEIGHT_FOR_OWN_SLICE);

  let slices: AssetSlice[];
  if (minor.length === 0) {
    slices = allSlices;
  } else {
    const othersValue = minor.reduce((sum, s) => sum + s.value, 0);
    const othersWeight = minor.reduce((sum, s) => sum + s.weight, 0);
    slices = [
      ...major,
      { label: "Outros", value: othersValue, weight: othersWeight },
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
