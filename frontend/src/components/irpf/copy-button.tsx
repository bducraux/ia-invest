"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { useToastContext } from "@/lib/toast-context";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  value: string;
  label?: string;
  successMessage?: string;
  size?: "sm" | "md";
  variant?: "ghost" | "outline";
  className?: string;
}

/**
 * Botão dedicado de copy-to-clipboard com feedback visual + toast.
 * Pensado para os campos do Simulador IR onde o usuário precisa colar
 * o valor exato no programa da Receita.
 */
export function CopyButton({
  value,
  label,
  successMessage,
  size = "sm",
  variant = "ghost",
  className,
}: CopyButtonProps) {
  const toast = useToastContext();
  const [copied, setCopied] = useState(false);

  const sizeClasses = size === "sm" ? "h-7 px-2 text-xs" : "h-9 px-3 text-sm";
  const variantClasses =
    variant === "outline"
      ? "border border-border bg-background hover:bg-accent"
      : "hover:bg-accent/60";

  async function handleClick() {
    try {
      // Usar Clipboard API quando disponível; fallback silencioso para execCommand.
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
      setCopied(true);
      const baseLabel = successMessage ?? "Valor copiado";
      // Mostra o valor copiado no toast — UX padrão Smartfolio. Trunca para
      // não estourar a largura quando for uma discriminação longa.
      const preview = value.length > 60 ? `${value.slice(0, 57)}…` : value;
      toast.success(`${baseLabel}: ${preview}`);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Não foi possível copiar para a área de transferência");
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md font-medium transition-colors",
        sizeClasses,
        variantClasses,
        className,
      )}
      aria-label={label ?? "Copiar"}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
      {label ? <span>{label}</span> : null}
    </button>
  );
}
