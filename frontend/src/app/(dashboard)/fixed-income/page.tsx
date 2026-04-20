"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, Plus, AlertTriangle, Info } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader, EmptyState } from "@/components/layout/page-header";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL } from "@/lib/money";
import { formatDate } from "@/lib/date";
import { usePortfolios } from "@/lib/queries";
import {
  createFixedIncomePosition,
  getFixedIncomePositions,
  importFixedIncomeCSV,
  type CreateFixedIncomeInput,
  type FixedIncomeImportResponse,
} from "@/lib/api";

type AssetType = "CDB" | "LCI" | "LCA";
type RemunerationType = "PRE" | "CDI_PERCENT";

const EMPTY_FORM: CreateFixedIncomeInput = {
  institution: "",
  assetType: "CDB",
  productName: "",
  remunerationType: "PRE",
  applicationDate: "",
  maturityDate: "",
  principalAppliedBrl: 0,
  fixedRateAnnualPercent: null,
  benchmarkPercent: null,
  liquidityLabel: null,
  notes: null,
};

export default function FixedIncomePage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioId = scope.portfolioId ?? portfolios[0]?.id;

  const queryClient = useQueryClient();
  const positionsQuery = useQuery({
    queryKey: ["fixed-income", portfolioId],
    queryFn: () => getFixedIncomePositions(portfolioId as string),
    enabled: Boolean(portfolioId),
  });

  const positions = useMemo(
    () => positionsQuery.data ?? [],
    [positionsQuery.data],
  );

  const totalInvested = useMemo(
    () => positions.reduce((sum, p) => sum + p.principalAppliedBrl, 0),
    [positions],
  );
  const totalGross = useMemo(
    () => positions.reduce((sum, p) => sum + p.grossValueCurrentBrl, 0),
    [positions],
  );
  const totalNet = useMemo(
    () => positions.reduce((sum, p) => sum + p.netValueCurrentBrl, 0),
    [positions],
  );

  const [form, setForm] = useState<CreateFixedIncomeInput>(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [importResult, setImportResult] =
    useState<FixedIncomeImportResponse | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createFixedIncomePosition(portfolioId as string, normalizeForm(form)),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["fixed-income", portfolioId] });
    },
  });

  const importMutation = useMutation({
    mutationFn: (file: File) =>
      importFixedIncomeCSV(portfolioId as string, file),
    onSuccess: (data) => {
      setImportResult(data);
      queryClient.invalidateQueries({ queryKey: ["fixed-income", portfolioId] });
    },
  });

  if (!portfolioId) {
    return (
      <>
        <TopBar title="Renda fixa" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Renda fixa"
            description="Aplicações bancárias (CDB, LCI, LCA) com cálculo de bruto e líquido."
          />
          <EmptyState
            title="Selecione um portfólio"
            description="Crie ou selecione um portfólio para registrar aplicações de renda fixa."
          />
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar title="Renda fixa" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Renda fixa"
          description="Aplicações bancárias brasileiras: CDB, LCI e LCA. Bruto e líquido recalculados sempre na data de hoje."
          actions={
            <>
              <Button onClick={() => setShowForm((v) => !v)} variant="outline">
                <Plus className="mr-2 h-4 w-4" />
                {showForm ? "Cancelar" : "Nova aplicação"}
              </Button>
              <label className="inline-flex cursor-pointer items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium ring-offset-background transition-colors hover:bg-accent hover:text-accent-foreground">
                <Upload className="mr-2 h-4 w-4" />
                Importar CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) importMutation.mutate(file);
                    event.target.value = "";
                  }}
                />
              </label>
            </>
          }
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              Avisos do MVP
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              IOF não é considerado nesta versão (decisão de produto do MVP).
            </p>
            <p className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              CDB: o valor líquido considera IR estimado com base na data atual.
            </p>
            <p className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              LCI/LCA: tratadas como isentas de IR para PF no modelo atual.
            </p>
          </CardContent>
        </Card>

        {showForm && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cadastrar aplicação</CardTitle>
              <CardDescription>
                Os campos são suficientes para o cálculo contratual. O bruto e o
                líquido são calculados pelo sistema.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FixedIncomeForm
                value={form}
                onChange={setForm}
                onSubmit={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                error={
                  createMutation.error instanceof Error
                    ? createMutation.error.message
                    : null
                }
              />
            </CardContent>
          </Card>
        )}

        {importResult && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resultado da importação</CardTitle>
              <CardDescription>
                {importResult.imported} aplicação(ões) importada(s),{" "}
                {importResult.failed} linha(s) com erro.
              </CardDescription>
            </CardHeader>
            {importResult.errors.length > 0 && (
              <CardContent>
                <ul className="space-y-1 text-sm text-destructive">
                  {importResult.errors.map((err, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>
                        Linha{" "}
                        {err.rowIndex !== null ? err.rowIndex + 2 : "—"}: {err.message}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            )}
          </Card>
        )}

        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard label="Aplicado" value={totalInvested} />
          <SummaryCard label="Bruto atual" value={totalGross} />
          <SummaryCard label="Líquido estimado hoje" value={totalNet} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Aplicações</CardTitle>
            <CardDescription>
              Cada linha = uma aplicação individual. Valores recalculados na data atual.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {positions.length === 0 ? (
              <EmptyState
                title="Nenhuma aplicação registrada"
                description="Cadastre manualmente ou importe um CSV com seus extratos bancários."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Instituição / Produto</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Remuneração</TableHead>
                    <TableHead>Aplicação</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead className="text-right">Aplicado</TableHead>
                    <TableHead className="text-right">Bruto atual</TableHead>
                    <TableHead className="text-right">IR estimado</TableHead>
                    <TableHead className="text-right">Líquido hoje</TableHead>
                    <TableHead>Faixa IR</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>
                        <div className="font-medium">{p.productName}</div>
                        <div className="text-xs text-muted-foreground">
                          {p.institution} · {p.daysSinceApplication}d
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{p.assetType}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {p.remunerationType === "PRE"
                          ? `Pré ${p.fixedRateAnnualPercent ?? 0}% a.a.`
                          : `${p.benchmarkPercent ?? 0}% do CDI`}
                      </TableCell>
                      <TableCell>{formatDate(p.applicationDate)}</TableCell>
                      <TableCell>{formatDate(p.maturityDate)}</TableCell>
                      <TableCell className="text-right">
                        {formatBRL(p.principalAppliedBrl)}
                      </TableCell>
                      <TableCell className="text-right">
                        {p.isComplete ? formatBRL(p.grossValueCurrentBrl) : "—"}
                        {!p.isComplete && (
                          <div
                            className="text-[10px] text-amber-500"
                            title={p.incompleteReason ?? ""}
                          >
                            cálculo incompleto
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatBRL(p.estimatedIrCurrentBrl)}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatBRL(p.netValueCurrentBrl)}
                      </TableCell>
                      <TableCell className="text-xs">
                        {p.taxBracketCurrent ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{formatBRL(value)}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function FixedIncomeForm({
  value,
  onChange,
  onSubmit,
  disabled,
  error,
}: {
  value: CreateFixedIncomeInput;
  onChange: (next: CreateFixedIncomeInput) => void;
  onSubmit: () => void;
  disabled: boolean;
  error: string | null;
}) {
  const update = <K extends keyof CreateFixedIncomeInput>(
    key: K,
    raw: CreateFixedIncomeInput[K],
  ) => onChange({ ...value, [key]: raw });

  return (
    <form
      className="grid gap-4 md:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <Field label="Instituição">
        <Input
          required
          value={value.institution}
          onChange={(e) => update("institution", e.target.value)}
        />
      </Field>
      <Field label="Nome do produto">
        <Input
          required
          value={value.productName}
          onChange={(e) => update("productName", e.target.value)}
        />
      </Field>
      <Field label="Tipo de ativo">
        <select
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={value.assetType}
          onChange={(e) => update("assetType", e.target.value as AssetType)}
        >
          <option value="CDB">CDB</option>
          <option value="LCI">LCI</option>
          <option value="LCA">LCA</option>
        </select>
      </Field>
      <Field label="Remuneração">
        <select
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={value.remunerationType}
          onChange={(e) =>
            update("remunerationType", e.target.value as RemunerationType)
          }
        >
          <option value="PRE">Prefixado</option>
          <option value="CDI_PERCENT">% do CDI</option>
        </select>
      </Field>
      <Field label="Data de aplicação">
        <Input
          type="date"
          required
          value={value.applicationDate}
          onChange={(e) => update("applicationDate", e.target.value)}
        />
      </Field>
      <Field label="Vencimento">
        <Input
          type="date"
          required
          value={value.maturityDate}
          onChange={(e) => update("maturityDate", e.target.value)}
        />
      </Field>
      <Field label="Valor aplicado (R$)">
        <Input
          type="number"
          min="0.01"
          step="0.01"
          required
          value={value.principalAppliedBrl ? value.principalAppliedBrl / 100 : ""}
          onChange={(e) =>
            update(
              "principalAppliedBrl",
              Math.round(Number(e.target.value || 0) * 100),
            )
          }
        />
      </Field>
      {value.remunerationType === "PRE" ? (
        <Field label="Taxa prefixada (% a.a.)">
          <Input
            type="number"
            step="0.01"
            required
            value={value.fixedRateAnnualPercent ?? ""}
            onChange={(e) =>
              update(
                "fixedRateAnnualPercent",
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
          />
        </Field>
      ) : (
        <Field label="% do CDI">
          <Input
            type="number"
            step="0.01"
            required
            value={value.benchmarkPercent ?? ""}
            onChange={(e) =>
              update(
                "benchmarkPercent",
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
          />
        </Field>
      )}
      <Field label="Liquidez (rótulo livre)">
        <Input
          value={value.liquidityLabel ?? ""}
          onChange={(e) =>
            update("liquidityLabel", e.target.value || null)
          }
        />
      </Field>
      <Field label="Observações">
        <Input
          value={value.notes ?? ""}
          onChange={(e) => update("notes", e.target.value || null)}
        />
      </Field>
      {error && (
        <p className="col-span-2 text-sm text-destructive">{error}</p>
      )}
      <div className="col-span-2">
        <Button type="submit" disabled={disabled}>
          {disabled ? "Salvando..." : "Salvar aplicação"}
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function normalizeForm(form: CreateFixedIncomeInput): CreateFixedIncomeInput {
  if (form.remunerationType === "PRE") {
    return { ...form, benchmark: "NONE", benchmarkPercent: null };
  }
  return { ...form, benchmark: "CDI", fixedRateAnnualPercent: null };
}
