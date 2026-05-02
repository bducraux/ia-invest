"use client";

import { Copy } from "lucide-react";
import { useState } from "react";
import { useToastContext } from "@/lib/toast-context";
import { cn } from "@/lib/utils";

interface IrpfFieldProps {
  /** Rótulo curto (ex.: "CNPJ", "Ativo", "Total"). */
  label: string;
  /** Valor exibido na tela. */
  display: string | null;
  /**
   * Conteúdo que vai para a área de transferência. Quando ausente, usa o
   * próprio ``display``. Use quando a string copiada é diferente da exibida
   * (ex.: ticker + nome juntos para colar em "Discriminação").
   */
  copyValue?: string;
  /** Mensagem do toast de sucesso. */
  copyLabel?: string;
  /** Texto a exibir quando ``display`` for null. */
  emptyText?: string;
  /** Renderiza com fonte monoespaçada (CNPJ, números). */
  mono?: boolean;
  /** Destaque visual para valores principais (ex.: Total). */
  highlight?: boolean;
  /** Largura mínima do campo. */
  minWidth?: string;
  /**
   * Texto exibido com destaque antes de ``display`` (ex.: ticker do ativo).
   * Não afeta o conteúdo copiado.
   */
  prefix?: string;
  className?: string;
}

/**
 * Campo padrão do Simulador IR: rótulo em cima, valor + ícone-only de copy
 * embaixo. Pensado para layout em grid limpo, sem botões com texto.
 *
 * Toast inclui o valor copiado (truncado), padrão Smartfolio.
 */
export function IrpfField({
  label,
  display,
  copyValue,
  copyLabel,
  emptyText = "—",
  mono = false,
  highlight = false,
  minWidth,
  prefix,
  className,
}: IrpfFieldProps) {
  const toast = useToastContext();
  const [copied, setCopied] = useState(false);
  const value = copyValue ?? display ?? "";
  const canCopy = Boolean(value);

  async function handleCopy() {
    if (!canCopy) return;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else if (typeof document !== "undefined") {
        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "absolute";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      const baseLabel = copyLabel ?? `${label} copiado`;
      const preview = value.length > 60 ? `${value.slice(0, 57)}…` : value;
      toast.success(`${baseLabel}: ${preview}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Não foi possível copiar para a área de transferência");
    }
  }

  return (
    <div
      className={cn("flex min-w-0 flex-col gap-0.5", className)}
      style={minWidth ? { minWidth } : undefined}
    >
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <button
        type="button"
        onClick={handleCopy}
        disabled={!canCopy}
        title={canCopy ? `Copiar ${label.toLowerCase()}` : undefined}
        className={cn(
          "group flex items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors",
          canCopy ? "hover:bg-accent/40" : "cursor-default",
        )}
      >
        <span
          className={cn(
            "flex min-w-0 items-baseline gap-1.5 truncate text-sm",
            mono && "font-mono tabular-nums",
            highlight && "font-semibold",
            !display && "italic text-muted-foreground",
          )}
        >
          {prefix ? (
            <span className="shrink-0 rounded-sm border border-border bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-foreground/80">
              {prefix}
            </span>
          ) : null}
          <span className="min-w-0 truncate">{display ?? emptyText}</span>
        </span>
        {canCopy ? (
          <Copy
            className={cn(
              "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors",
              copied
                ? "text-emerald-500"
                : "opacity-50 group-hover:opacity-100",
            )}
          />
        ) : null}
      </button>
    </div>
  );
}
