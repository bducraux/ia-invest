"use client";

import type { IrpfRow } from "@/lib/api";
import { formatNumberPtBr } from "@/lib/money";
import { IrpfField } from "./irpf-field";
import { WarningBadge } from "./warning-badge";

interface IrpfRowCardProps {
  row: IrpfRow;
}

/**
 * Linha de Rendimentos (cód. 09 / 10 / 18 / 99) — layout enxuto: cada campo
 * tem rótulo + valor + ícone de copiar. Sem botões com texto e sem labels
 * redundantes. O usuário identifica visualmente o que precisa colar onde.
 */
export function IrpfRowCard({ row }: IrpfRowCardProps) {
  const valueText = formatNumberPtBr(row.value_cents);
  const assetName = row.asset_name ?? row.asset_code;
  const assetNameForCopy = `${row.asset_code} ${assetName}`.trim();

  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2 rounded-lg border border-border/60 bg-card/40 px-4 py-3">
      <IrpfField
        label="CNPJ"
        display={row.cnpj}
        emptyText="pendente"
        mono
        minWidth="170px"
      />
      <IrpfField
        label="Ativo"
        display={assetName}
        prefix={row.asset_code}
        copyValue={assetNameForCopy}
        copyLabel="Ativo copiado"
        minWidth="240px"
        className="flex-1"
      />
      <IrpfField
        label="Valor"
        display={valueText}
        copyLabel="Valor copiado"
        mono
        highlight
        minWidth="110px"
        className="items-end text-right"
      />
      {row.warnings.length > 0 ? (
        <div className="self-center">
          <WarningBadge warnings={row.warnings} />
        </div>
      ) : null}
    </div>
  );
}
