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

// Ordenado para maximizar contraste entre posições adjacentes:
// matizes saltam ~120° entre vizinhos para evitar cores parecidas em fatias próximas.
const COLORS = [
  "hsl(158 64% 52%)", // 1 verde
  "hsl(280 70% 65%)", // 2 roxo
  "hsl(38 92% 60%)",  // 3 laranja
  "hsl(199 89% 60%)", // 4 azul
  "hsl(0 72% 60%)",   // 5 vermelho
  "hsl(48 95% 55%)",  // 6 amarelo
  "hsl(262 70% 70%)", // 7 violeta
  "hsl(96 55% 55%)",  // 8 verde-amarelado
  "hsl(330 75% 65%)", // 9 rosa
  "hsl(173 58% 45%)", // 10 verde-azulado
  "hsl(15 85% 62%)",  // 11 vermelho-alaranjado
  "hsl(220 14% 60%)", // 12 cinza-azul
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
