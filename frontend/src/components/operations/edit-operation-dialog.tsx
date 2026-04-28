"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { OperationUpdateInput } from "@/lib/api";

export interface EditableOperation {
  id: number;
  portfolioId: string;
  date: string;
  assetCode: string;
  quantity: number;
  unitPriceBrl: number; // BRL units (not cents)
  totalBrl: number; // BRL units (not cents)
}

interface EditOperationDialogProps {
  open: boolean;
  operation: EditableOperation | null;
  busy?: boolean;
  onCancel: () => void;
  onSave: (patch: OperationUpdateInput) => void;
}

interface FormState {
  operationDate: string;
  assetCode: string;
  quantity: string;
  unitPriceBrl: string;
  totalBrl: string;
  notes: string;
}

function toFormState(op: EditableOperation): FormState {
  return {
    operationDate: op.date,
    assetCode: op.assetCode,
    quantity: String(op.quantity),
    unitPriceBrl: op.unitPriceBrl.toFixed(2),
    totalBrl: op.totalBrl.toFixed(2),
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

export function EditOperationDialog({
  open,
  operation,
  busy = false,
  onCancel,
  onSave,
}: EditOperationDialogProps) {
  const [form, setForm] = useState<FormState | null>(
    operation ? toFormState(operation) : null,
  );
  const [lastOpId, setLastOpId] = useState<number | null>(operation?.id ?? null);

  if ((operation?.id ?? null) !== lastOpId) {
    setLastOpId(operation?.id ?? null);
    setForm(operation ? toFormState(operation) : null);
  }

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open || !operation || !form) return null;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form || !operation) return;
    const patch: OperationUpdateInput = {};
    if (form.operationDate !== operation.date) {
      patch.operationDate = form.operationDate;
    }
    if (form.assetCode !== operation.assetCode) {
      patch.assetCode = form.assetCode.trim();
    }
    const quantity = Number(form.quantity.replace(",", "."));
    if (Number.isFinite(quantity) && quantity !== operation.quantity) {
      patch.quantity = quantity;
    }
    const unitCents = brlToCents(form.unitPriceBrl);
    if (
      unitCents !== null &&
      unitCents !== Math.round(operation.unitPriceBrl * 100)
    ) {
      patch.unitPrice = unitCents;
    }
    const totalCents = brlToCents(form.totalBrl);
    if (
      totalCents !== null &&
      totalCents !== Math.round(operation.totalBrl * 100)
    ) {
      patch.grossValue = totalCents;
    }
    if (form.notes.trim() !== "") {
      patch.notes = form.notes.trim();
    }
    onSave(patch);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-operation-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-lg border border-border bg-background p-6 shadow-xl"
      >
        <header>
          <h2
            id="edit-operation-title"
            className="text-lg font-semibold text-foreground"
          >
            Editar operação #{operation.id}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Editar uma operação importada anula seu identificador externo para
            não conflitar com futuras reimportações da mesma origem.
          </p>
        </header>

        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1 text-sm">
            <span className="text-foreground">Data</span>
            <Input
              type="date"
              value={form.operationDate}
              onChange={(e) => update("operationDate", e.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-foreground">Ativo</span>
            <Input
              value={form.assetCode}
              onChange={(e) => update("assetCode", e.target.value.toUpperCase())}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-foreground">Quantidade</span>
            <Input
              inputMode="decimal"
              value={form.quantity}
              onChange={(e) => update("quantity", e.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-foreground">Preço unitário (R$)</span>
            <Input
              inputMode="decimal"
              value={form.unitPriceBrl}
              onChange={(e) => update("unitPriceBrl", e.target.value)}
            />
          </label>
          <label className="col-span-2 space-y-1 text-sm">
            <span className="text-foreground">Total (R$)</span>
            <Input
              inputMode="decimal"
              value={form.totalBrl}
              onChange={(e) => update("totalBrl", e.target.value)}
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

        <footer className="flex justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={busy}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Salvando..." : "Salvar alterações"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
