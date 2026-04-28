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
import { getSliceColor } from "@/lib/chart-colors";

const MIN_WEIGHT_FOR_OWN_SLICE = 0.005;
const MAX_INDIVIDUAL_SLICES = 15;

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

  const major: AssetSlice[] = [];
  const minor: AssetSlice[] = [];
  for (const slice of allSlices) {
    if (
      major.length < MAX_INDIVIDUAL_SLICES &&
      slice.weight >= MIN_WEIGHT_FOR_OWN_SLICE
    ) {
      major.push(slice);
    } else {
      minor.push(slice);
    }
  }

  let slices: AssetSlice[];
  if (minor.length === 0) {
    slices = major;
  } else if (minor.length === 1) {
    slices = [...major, minor[0]];
  } else {
    const othersValue = minor.reduce((sum, s) => sum + s.value, 0);
    const othersWeight = minor.reduce((sum, s) => sum + s.weight, 0);
    slices = [
      ...major,
      { label: `Outros (${minor.length})`, value: othersValue, weight: othersWeight },
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
          {slices.map((slice, i) => (
            <Cell key={i} fill={getSliceColor(slice.label, i)} />
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
