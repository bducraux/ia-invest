"use client";

import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { AllocationSlice } from "@/types/domain";
import { formatBRL, formatPercent } from "@/lib/money";

const COLORS = [
  "hsl(158 64% 52%)",
  "hsl(199 89% 60%)",
  "hsl(38 92% 60%)",
  "hsl(280 70% 65%)",
  "hsl(220 14% 60%)",
  "hsl(0 72% 60%)",
];

export function AllocationDonut({ data }: { data: AllocationSlice[] }) {
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
          {data.map((_, i) => (
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
            const slice = item.payload as AllocationSlice;
            const cents = Number(value) || 0;
            return [
              `${formatBRL(cents)} · ${formatPercent(slice.weight)}`,
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
