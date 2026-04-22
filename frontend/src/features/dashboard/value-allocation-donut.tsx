"use client";

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { formatBRL, formatPercent } from "@/lib/money";

const OTHERS_COLOR = "hsl(220 8% 52%)";

function getSliceColor(slice: ValueAllocationSlice, index: number): string {
  if (slice.label.trim().toLowerCase() === "outros") {
    return OTHERS_COLOR;
  }

  // Golden-angle hue distribution reduces visual collisions when there are many slices.
  const hue = Math.round((index * 137.508) % 360);
  const saturation = 62 + (index % 3) * 8;
  const lightness = 44 + (index % 2) * 10;

  return `hsl(${hue} ${saturation}% ${lightness}%)`;
}

export interface ValueAllocationSlice {
  label: string;
  value: number;
  weight: number;
}

export function ValueAllocationDonut({ data }: { data: ValueAllocationSlice[] }) {
  if (data.length === 0) {
    return (
      <div className="flex h-[260px] items-center justify-center text-sm text-muted-foreground">
        Sem dados para exibir
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius={60}
          outerRadius={95}
          paddingAngle={2}
          stroke="none"
        >
          {data.map((slice, index) => (
            <Cell key={index} fill={getSliceColor(slice, index)} />
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
            const slice = item.payload as ValueAllocationSlice;
            return [
              `${formatBRL(Number(value) || 0)} · ${formatPercent(slice.weight)}`,
              slice.label,
            ];
          }}
        />
        <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
