"use client";

import { useEffect, useId, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { OperationCreateInput } from "@/lib/api";
import { usePortfolioPositions } from "@/lib/queries";
import type { Portfolio } from "@/types/domain";

interface CreateOperationDialogProps {
  open: boolean;
  portfolios: Portfolio[];
  defaultPortfolioId: string | null;
  busy?: boolean;
  onCancel: () => void;
  onSave: (portfolioId: string, input: OperationCreateInput) => void;
}

interface FormState {
  operationDate: string;
  assetCode: string;
  assetType: string;
  operationType: string;
  quantity: string;
  unitPriceBrl: string;
  totalBrl: string;
  totalAuto: boolean;
  feesBrl: string;
  notes: string;
}

const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: "Ação",
  fii: "FII",
  etf: "ETF",
  bdr: "BDR",
  stock_us: "Ação (US)",
  etf_us: "ETF (US)",
  reit_us: "REIT (US)",
  bdr_us: "BDR (US)",
  crypto: "Cripto",
  CDB: "CDB",
  LCI: "LCI",
  LCA: "LCA",
  previdencia: "Previdência",
};

const OPERATION_TYPES_BY_FAMILY: Record<
  string,
  ReadonlyArray<{ value: string; label: string }>
> = {
  RENDA_VARIAVEL: [
    { value: "buy", label: "Compra" },
    { value: "sell", label: "Venda" },
    { value: "dividend", label: "Dividendo" },
    { value: "jcp", label: "JCP" },
    { value: "rendimento", label: "Rendimento" },
    { value: "split_bonus", label: "Split / Bonificação" },
  ],
  CRIPTO: [
    { value: "buy", label: "Compra" },
    { value: "sell", label: "Venda" },
    { value: "transfer_in", label: "Transferência in" },
    { value: "transfer_out", label: "Transferência out" },
    { value: "rendimento", label: "Rendimento" },
  ],
  INTERNACIONAL: [
    { value: "buy", label: "Compra" },
    { value: "sell", label: "Venda" },
    { value: "dividend", label: "Dividendo" },
  ],
  PREVIDENCIA: [
    { value: "buy", label: "Aporte" },
    { value: "sell", label: "Resgate" },
    { value: "rendimento", label: "Rendimento" },
  ],
  RENDA_FIXA: [
    { value: "buy", label: "Aplicação" },
    { value: "sell", label: "Resgate" },
    { value: "rendimento", label: "Rendimento" },
  ],
  GENERIC: [
    { value: "buy", label: "Compra" },
    { value: "sell", label: "Venda" },
    { value: "dividend", label: "Dividendo" },
    { value: "jcp", label: "JCP" },
    { value: "rendimento", label: "Rendimento" },
    { value: "transfer_in", label: "Transferência in" },
    { value: "transfer_out", label: "Transferência out" },
    { value: "split_bonus", label: "Split / Bonificação" },
  ],
};

// Mapeia a `assetClass` (UI) -> `asset_type` raw mais provável,
// usado para auto-preencher a classe quando o usuário escolhe um ativo já existente.
const UI_CLASS_TO_RAW_TYPE: Record<string, string> = {
  ACAO: "stock",
  FII: "fii",
  ETF: "etf",
  BDR: "bdr",
  CRIPTO: "crypto",
  INTERNACIONAL: "stock_us",
  RENDA_FIXA: "CDB",
  PREVIDENCIA: "previdencia",
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function emptyForm(defaultAssetType: string, defaultOpType: string): FormState {
  return {
    operationDate: todayIso(),
    assetCode: "",
    assetType: defaultAssetType,
    operationType: defaultOpType,
    quantity: "",
    unitPriceBrl: "",
    totalBrl: "",
    totalAuto: true,
    feesBrl: "",
    notes: "",
  };
}

function brlToCents(value: string): number | null {
  const normalised = value.replace(",", ".").trim();
  if (normalised === "") return null;
  const parsed = Number(normalised);
  if (!Number.isFinite(parsed)) return null;
  return Math.round(parsed * 100);
}

function parseQuantity(value: string): number | null {
  const normalised = value.replace(",", ".").trim();
  if (normalised === "") return null;
  const parsed = Number(normalised);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

function computeAutoTotal(quantity: string, unitPriceBrl: string): string {
  const q = parseQuantity(quantity);
  const p = brlToCents(unitPriceBrl);
  if (q === null || p === null) return "";
  const cents = Math.round(Math.abs(q) * p);
  return (cents / 100).toFixed(2);
}

export function CreateOperationDialog({
  open,
  portfolios,
  defaultPortfolioId,
  busy = false,
  onCancel,
  onSave,
}: CreateOperationDialogProps) {
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(
    defaultPortfolioId,
  );

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => p.id === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );
  const allowedTypes = selectedPortfolio?.allowedAssetTypes ?? [];
  const defaultAssetType = allowedTypes[0] ?? "stock";
  const opTypes =
    OPERATION_TYPES_BY_FAMILY[selectedPortfolio?.specialization ?? "GENERIC"] ??
    OPERATION_TYPES_BY_FAMILY.GENERIC;
  const defaultOpType = opTypes[0]?.value ?? "buy";

  const [form, setForm] = useState<FormState>(() =>
    emptyForm(defaultAssetType, defaultOpType),
  );
  const [error, setError] = useState<string | null>(null);
  const [wasOpen, setWasOpen] = useState(false);

  // Quando o diálogo abre, sincroniza com defaultPortfolioId e reseta o form.
  if (open && !wasOpen) {
    setWasOpen(true);
    if (defaultPortfolioId !== selectedPortfolioId) {
      setSelectedPortfolioId(defaultPortfolioId);
    }
    setForm(emptyForm(defaultAssetType, defaultOpType));
    setError(null);
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  // Reset form ao trocar de carteira manualmente com o diálogo aberto.
  const [lastSelectedKey, setLastSelectedKey] = useState<string | null>(
    selectedPortfolioId,
  );
  if (open && selectedPortfolioId !== lastSelectedKey) {
    setLastSelectedKey(selectedPortfolioId);
    setForm(emptyForm(defaultAssetType, defaultOpType));
    setError(null);
  }

  // Datalist de ativos da carteira selecionada para autocomplete.
  const positionsQuery = usePortfolioPositions(
    selectedPortfolioId ?? undefined,
    false,
  );
  const assetSuggestions = positionsQuery.data ?? [];
  const datalistId = useId();

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;
  if (portfolios.length === 0) return null;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleQuantityChange(value: string) {
    setForm((prev) => ({
      ...prev,
      quantity: value,
      totalBrl: prev.totalAuto
        ? computeAutoTotal(value, prev.unitPriceBrl)
        : prev.totalBrl,
    }));
  }

  function handleUnitPriceChange(value: string) {
    setForm((prev) => ({
      ...prev,
      unitPriceBrl: value,
      totalBrl: prev.totalAuto
        ? computeAutoTotal(prev.quantity, value)
        : prev.totalBrl,
    }));
  }

  function handleTotalChange(value: string) {
    setForm((prev) => ({ ...prev, totalBrl: value, totalAuto: false }));
  }

  function handleResetAutoTotal() {
    setForm((prev) => ({
      ...prev,
      totalAuto: true,
      totalBrl: computeAutoTotal(prev.quantity, prev.unitPriceBrl),
    }));
  }

  function handleAssetCodeChange(value: string) {
    const upper = value.toUpperCase();
    const match = assetSuggestions.find((p) => p.assetCode === upper);
    setForm((prev) => {
      let nextType = prev.assetType;
      if (match) {
        const mapped = UI_CLASS_TO_RAW_TYPE[match.assetClass];
        if (mapped && allowedTypes.includes(mapped)) nextType = mapped;
      }
      return { ...prev, assetCode: upper, assetType: nextType };
    });
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!selectedPortfolioId) {
      setError("Selecione uma carteira.");
      return;
    }
    const assetCode = form.assetCode.trim().toUpperCase();
    if (!assetCode) {
      setError("Informe o código do ativo.");
      return;
    }
    const quantity = parseQuantity(form.quantity);
    if (quantity === null) {
      setError("Quantidade inválida.");
      return;
    }
    const unitCents = brlToCents(form.unitPriceBrl);
    if (unitCents === null) {
      setError("Preço unitário inválido.");
      return;
    }
    const totalCentsRaw = brlToCents(form.totalBrl);
    const grossCents =
      totalCentsRaw ?? Math.round(Math.abs(quantity) * unitCents);
    const feesCents = brlToCents(form.feesBrl) ?? 0;

    const input: OperationCreateInput = {
      assetCode,
      assetType: form.assetType,
      operationType: form.operationType,
      operationDate: form.operationDate,
      quantity,
      unitPrice: unitCents,
      grossValue: grossCents,
      fees: feesCents,
    };
    if (form.notes.trim()) input.notes = form.notes.trim();
    onSave(selectedPortfolioId, input);
  }

  const showPortfolioPicker = portfolios.length > 1 && defaultPortfolioId === null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-operation-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-lg space-y-4 rounded-lg border border-border bg-background p-6 shadow-xl"
      >
        <header>
          <h2
            id="create-operation-title"
            className="text-lg font-semibold text-foreground"
          >
            Nova operação{selectedPortfolio ? ` — ${selectedPortfolio.name}` : ""}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Operação manual: a posição do ativo será recalculada após salvar.
            O nome do ativo é resolvido automaticamente a partir da origem dos dados.
          </p>
        </header>

        {showPortfolioPicker ? (
          <label className="block space-y-1 text-sm">
            <span className="text-foreground">Carteira</span>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
              value={selectedPortfolioId ?? ""}
              onChange={(e) => setSelectedPortfolioId(e.target.value || null)}
              required
            >
              <option value="" disabled>
                Selecione...
              </option>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {!selectedPortfolio ? (
          <p className="text-sm text-muted-foreground">
            Selecione uma carteira para continuar.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Data</span>
              <Input
                type="date"
                value={form.operationDate}
                onChange={(e) => update("operationDate", e.target.value)}
                required
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Tipo</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={form.operationType}
                onChange={(e) => update("operationType", e.target.value)}
              >
                {opTypes.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Ativo</span>
              <Input
                list={datalistId}
                value={form.assetCode}
                onChange={(e) => handleAssetCodeChange(e.target.value)}
                placeholder={
                  assetSuggestions.length > 0
                    ? `Ex.: ${assetSuggestions[0]?.assetCode}`
                    : "Código do ativo"
                }
                required
                autoComplete="off"
              />
              <datalist id={datalistId}>
                {assetSuggestions.map((p) => (
                  <option key={p.assetCode} value={p.assetCode}>
                    {p.name}
                  </option>
                ))}
              </datalist>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Classe</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={form.assetType}
                onChange={(e) => update("assetType", e.target.value)}
                disabled={allowedTypes.length === 0}
              >
                {allowedTypes.length === 0 ? (
                  <option value="">— sem classes definidas —</option>
                ) : null}
                {allowedTypes.map((t) => (
                  <option key={t} value={t}>
                    {ASSET_TYPE_LABELS[t] ?? t}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Quantidade</span>
              <Input
                inputMode="decimal"
                value={form.quantity}
                onChange={(e) => handleQuantityChange(e.target.value)}
                required
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Preço unitário (R$)</span>
              <Input
                inputMode="decimal"
                value={form.unitPriceBrl}
                onChange={(e) => handleUnitPriceChange(e.target.value)}
                required
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">
                Total (R$){" "}
                {form.totalAuto ? (
                  <span className="text-xs text-muted-foreground">(auto)</span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResetAutoTotal}
                    className="text-xs text-primary underline"
                  >
                    voltar para auto
                  </button>
                )}
              </span>
              <Input
                inputMode="decimal"
                value={form.totalBrl}
                onChange={(e) => handleTotalChange(e.target.value)}
                placeholder="Calculado a partir de qtd × preço"
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-foreground">Taxas (R$)</span>
              <Input
                inputMode="decimal"
                value={form.feesBrl}
                onChange={(e) => update("feesBrl", e.target.value)}
                placeholder="0,00"
              />
            </label>
            <label className="col-span-2 space-y-1 text-sm">
              <span className="text-foreground">Notas</span>
              <Input
                value={form.notes}
                onChange={(e) => update("notes", e.target.value)}
                placeholder="Anotação opcional"
              />
            </label>
          </div>
        )}

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        <footer className="flex justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={busy}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={busy || !selectedPortfolio}>
            {busy ? "Salvando..." : "Criar operação"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
