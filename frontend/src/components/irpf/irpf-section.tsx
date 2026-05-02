"use client";

import type { IrpfSection } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { IrpfBemDireitoRowCard } from "./irpf-bem-direito-row";
import { IrpfRowCard } from "./irpf-row";

interface IrpfSectionCardProps {
  section: IrpfSection;
}

/**
 * Formata o código da seção:
 * - Rendimentos (cód. simples como "09", "10", "18", "99") → exibe inteiro.
 * - Bens e Direitos (cód. composto como "03-01", "99-07") → exibe
 *   "GG ▷ CC" (Grupo ▷ Código), seguindo o padrão da Receita.
 */
function formatSectionCode(code: string): string {
  const parts = code.split("-");
  if (parts.length === 2) return `${parts[0]} ▷ ${parts[1]}`;
  return code;
}

export function IrpfSectionCard({ section }: IrpfSectionCardProps) {
  const isComposite = section.code.includes("-");
  const codeTitle = isComposite ? "Grupo / Código" : undefined;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span
            title={codeTitle}
            className="rounded-md bg-primary/15 px-2 py-0.5 font-mono text-xs text-primary"
          >
            {formatSectionCode(section.code)}
          </span>
          <CardTitle className="text-base font-semibold text-foreground">
            {section.title}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {section.rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum lançamento nesta seção para o ano-base selecionado.
          </p>
        ) : section.category === "bem_direito" ? (
          section.rows.map((row) => (
            <IrpfBemDireitoRowCard key={row.asset_code} row={row} />
          ))
        ) : (
          section.rows.map((row) => (
            <IrpfRowCard key={`${section.code}-${row.asset_code}`} row={row} />
          ))
        )}
      </CardContent>
    </Card>
  );
}
