"use client";

import { AlertTriangle } from "lucide-react";

const WARNING_LABELS: Record<string, string> = {
  cnpj_missing: "CNPJ ausente — preencha em Cadastro de Ativos",
  valor_zero: "Valor zerado — confira a operação de origem",
  posicao_zerada_no_ano:
    "Posição zerada no ano — declare como 'situação em 31/12: 0,00' para zerar o bem",
  asset_metadata_missing:
    "Metadados de ativo faltando — informe a classe IRPF (ação/FII/etc.)",
};

function describe(warning: string): string {
  // Suporta a forma "asset_metadata_missing:CODE1,CODE2".
  const [code, payload] = warning.split(":", 2);
  const base = WARNING_LABELS[code] ?? warning;
  return payload ? `${base} (${payload})` : base;
}

interface WarningBadgeProps {
  warnings: string[];
}

export function WarningBadge({ warnings }: WarningBadgeProps) {
  if (warnings.length === 0) return null;
  const tooltip = warnings.map(describe).join("\n");
  return (
    <span
      title={tooltip}
      className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-400"
    >
      <AlertTriangle className="h-3 w-3" />
      {warnings.length === 1 ? "atenção" : `${warnings.length} alertas`}
    </span>
  );
}
