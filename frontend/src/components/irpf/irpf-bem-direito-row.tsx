"use client";

import type { IrpfRow } from "@/lib/api";
import { formatNumberPtBr } from "@/lib/money";
import { CopyButton } from "./copy-button";
import { IrpfField } from "./irpf-field";
import { WarningBadge } from "./warning-badge";

interface IrpfBemDireitoRowCardProps {
  row: IrpfRow;
}

function formatQuantityForBem(qty: number): string {
  if (Number.isInteger(qty)) {
    return new Intl.NumberFormat("pt-BR").format(qty);
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 8 }).format(qty);
}

/**
 * Linha de Bens e Direitos (cód. 03-01 / 07-03 / 07-02) — layout enxuto:
 * todos os campos rotulados, sem labels redundantes. Mostra apenas o que
 * o usuário precisa para preencher a Receita: CNPJ, Ativo, Qtd., P. médio,
 * Total. A discriminação fica disponível só por trás do ícone (clique copia).
 */
export function IrpfBemDireitoRowCard({ row }: IrpfBemDireitoRowCardProps) {
  const extra = row.extra;
  const totalText = formatNumberPtBr(row.value_cents);
  const avgPriceText = extra ? formatNumberPtBr(extra.avg_price_cents) : null;
  const quantityText = extra ? formatQuantityForBem(extra.quantity) : null;
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
        label="Qtd."
        display={quantityText}
        copyLabel="Quantidade copiada"
        mono
        minWidth="80px"
      />
      <IrpfField
        label="P. médio"
        display={avgPriceText}
        copyLabel="Preço médio copiado"
        mono
        minWidth="90px"
      />
      <IrpfField
        label="Total"
        display={totalText}
        copyLabel="Total copiado"
        mono
        highlight
        minWidth="110px"
        className="items-end text-right"
      />
      {row.discriminacao ? (
        <div className="self-end pb-0.5">
          <CopyButton
            value={row.discriminacao}
            size="sm"
            variant="outline"
            className="h-7 px-1.5"
            successMessage="Discriminação copiada"
          />
        </div>
      ) : null}
      {row.warnings.length > 0 ? (
        <div className="self-center">
          <WarningBadge warnings={row.warnings} />
        </div>
      ) : null}
    </div>
  );
}
