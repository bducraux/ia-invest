"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { Upload, Plus, AlertTriangle, Wallet } from "lucide-react";
import Link from "next/link";

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
import { buildScopedPath, useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL } from "@/lib/money";
import { formatDate } from "@/lib/date";
import { usePortfolios } from "@/lib/queries";
import {
  createFixedIncomePosition,
  getFixedIncomePositions,
  importFixedIncomeCSV,
  type CreateFixedIncomeInput,
  type FixedIncomeImportResponse,
  type FixedIncomePosition,
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

type FixedIncomePositionWithPortfolio = FixedIncomePosition & {
  portfolioId: string;
  portfolioName: string;
};

const EMPTY_LIST: FixedIncomePosition[] = [];

export default function FixedIncomePage() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = useMemo(() => portfoliosQuery.data ?? [], [portfoliosQuery.data]);
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);
  const visiblePortfolios = useMemo(
    () => (
      scope.isGlobalScope
        ? portfolios
        : activePortfolio
          ? [activePortfolio]
          : []
    ),
    [scope.isGlobalScope, portfolios, activePortfolio],
  );
  const [preferredPortfolioId, setPreferredPortfolioId] = useState<string>("");

  const queryClient = useQueryClient();

  const positionQueries = useQueries({
    queries: visiblePortfolios.map((portfolio) => ({
      queryKey: ["fixed-income", portfolio.id],
      queryFn: () => getFixedIncomePositions(portfolio.id),
      enabled: Boolean(portfolio.id),
    })),
  });

  const targetPortfolioId = scope.isGlobalScope
    ? portfolios.some((portfolio) => portfolio.id === preferredPortfolioId)
      ? preferredPortfolioId
      : portfolios[0]?.id ?? ""
    : activePortfolio?.id ?? "";
  const targetPortfolio = portfolios.find((portfolio) => portfolio.id === targetPortfolioId);

  const positions = useMemo<FixedIncomePositionWithPortfolio[]>(
    () =>
      visiblePortfolios.flatMap((portfolio, index) =>
        (positionQueries[index]?.data ?? []).map((position) => ({
          ...position,
          portfolioId: portfolio.id,
          portfolioName: portfolio.name,
        })),
      ),
    [visiblePortfolios, positionQueries],
  );

  const portfolioSummaries = useMemo(
    () =>
      visiblePortfolios
        .map((portfolio, index) => {
          const list = positionQueries[index]?.data ?? EMPTY_LIST;
          const applied = list.reduce((sum, position) => sum + position.principalAppliedBrl, 0);
          const gross = list.reduce((sum, position) => sum + position.grossValueCurrentBrl, 0);
          const net = list.reduce((sum, position) => sum + position.netValueCurrentBrl, 0);

          return {
            portfolioId: portfolio.id,
            portfolioName: portfolio.name,
            count: list.length,
            applied,
            gross,
            net,
          };
        })
        .filter((summary) => summary.count > 0)
        .sort((left, right) => right.net - left.net),
    [visiblePortfolios, positionQueries],
  );

  const hasIncompleteValuation = useMemo(
    () => positions.some((position) => !position.isComplete),
    [positions],
  );

  const isLoading = portfoliosQuery.isLoading || positionQueries.some((query) => query.isLoading);
  const error = positionQueries.find((query) => query.error)?.error;

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
      createFixedIncomePosition(targetPortfolioId, normalizeForm(form)),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["fixed-income", targetPortfolioId] });
    },
  });

  const importMutation = useMutation({
    mutationFn: (file: File) =>
      importFixedIncomeCSV(targetPortfolioId, file),
    onSuccess: (data) => {
      setImportResult(data);
      queryClient.invalidateQueries({ queryKey: ["fixed-income", targetPortfolioId] });
    },
  });

  if (portfoliosQuery.isLoading) {
    return (
      <>
        <TopBar title="Renda fixa" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Renda fixa"
            description="Carregando aplicações de renda fixa."
          />
        </main>
      </>
    );
  }

  if (!portfolios.length) {
    return (
      <>
        <TopBar title="Renda fixa" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Renda fixa"
            description="Aplicações bancárias (CDB, LCI, LCA) com cálculo de bruto e líquido."
          />
          <EmptyState
            title="Selecione uma carteira"
            description="Crie ou selecione uma carteira para registrar aplicações de renda fixa."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Renda fixa" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Renda fixa"
            description="Selecione uma carteira válida na navegação lateral."
          />
        </main>
      </>
    );
  }

  const pageTitle = scope.isGlobalScope
    ? "Renda fixa"
    : `Renda fixa - ${activePortfolio?.name}`;
  const pageDescription = scope.isGlobalScope
    ? "Visão consolidada das aplicações bancárias da família."
    : `Aplicações de renda fixa da carteira ${activePortfolio?.name}.`;

  return (
    <>
      <TopBar title="Renda fixa" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title={pageTitle}
          description={pageDescription}
          actions={
            <>
              {scope.isGlobalScope ? (
                <label className="flex min-w-52 flex-col gap-1 text-xs text-muted-foreground">
                  Carteira de destino
                  <select
                    className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                    value={targetPortfolioId}
                    onChange={(event) => setPreferredPortfolioId(event.target.value)}
                  >
                    {portfolios.map((portfolio) => (
                      <option key={portfolio.id} value={portfolio.id}>
                        {portfolio.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
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

        {showForm && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cadastrar aplicação</CardTitle>
              <CardDescription>
                A aplicação será registrada em {targetPortfolio?.name ?? "uma carteira"}. Os campos são suficientes para o cálculo contratual.
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
                {targetPortfolio?.name ?? "Carteira selecionada"}: {importResult.imported} aplicação(ões) importada(s),{" "}
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
          <SummaryCard label="Líquido para resgate hoje" value={totalNet} highlight />
          <SummaryCard label="Bruto atual (antes de IR)" value={totalGross} />
          <SummaryCard label="Aplicado" value={totalInvested} />
        </div>

        {hasIncompleteValuation ? (
          <Card className="border-amber-500/50 bg-amber-50/40">
            <CardHeader>
              <CardTitle className="text-base text-amber-900">Erro de regra de negócio: cálculo incompleto</CardTitle>
              <CardDescription className="text-amber-800">
                Existem aplicações sem cálculo completo de CDI. Configure a taxa anual em Configurações &gt; Taxas de Referência
                para permitir o cálculo diário automático e reprocessar os valores.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : null}

        {scope.isGlobalScope ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Carteiras com renda fixa</CardTitle>
              <CardDescription>
                Panorama por carteira para facilitar leitura do patrimônio consolidado.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {portfolioSummaries.length === 0 ? (
                <EmptyState
                  title="Nenhuma carteira com renda fixa"
                  description="Cadastre uma aplicação ou importe um CSV para começar a consolidar essa visão."
                />
              ) : (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {portfolioSummaries.map((summary) => (
                    <Link
                      key={summary.portfolioId}
                      href={buildScopedPath(summary.portfolioId, "/")}
                      className="rounded-xl border border-border bg-muted/20 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium text-foreground">{summary.portfolioName}</p>
                          <p className="text-sm text-muted-foreground">
                            {summary.count} aplicaç{summary.count === 1 ? "ão" : "ões"}
                          </p>
                        </div>
                        {summary.portfolioId === targetPortfolioId ? (
                          <Badge variant="outline">Destino</Badge>
                        ) : (
                          <Badge variant="muted">Abrir</Badge>
                        )}
                      </div>
                      <dl className="mt-4 space-y-2 text-sm">
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-muted-foreground">Aplicado</dt>
                          <dd className="font-medium">{formatBRL(summary.applied)}</dd>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-muted-foreground">Bruto</dt>
                          <dd className="font-medium">{formatBRL(summary.gross)}</dd>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <dt className="text-muted-foreground">Líquido</dt>
                          <dd className="font-medium">{formatBRL(summary.net)}</dd>
                        </div>
                      </dl>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Aplicações</CardTitle>
            <CardDescription>
              Cada linha representa uma aplicação individual em alguma carteira. Valores recalculados na data atual.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <EmptyState
                title="Carregando aplicações"
                description={
                  scope.isGlobalScope
                    ? "Buscando renda fixa em todas as carteiras cadastradas."
                    : `Buscando renda fixa da carteira ${activePortfolio?.name}.`
                }
              />
            ) : error instanceof Error ? (
              <EmptyState
                title="Não foi possível carregar a renda fixa"
                description={error.message}
              />
            ) : positions.length === 0 ? (
              <EmptyState
                title="Nenhuma aplicação registrada"
                description="Cadastre manualmente ou importe um CSV com seus extratos bancários."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
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
                    <TableRow key={`${p.portfolioId}-${p.id}`}>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Wallet className="h-4 w-4 text-muted-foreground" />
                            <span>{p.portfolioName}</span>
                          </div>
                        </TableCell>
                      ) : null}
                      <TableCell>
                        <div className="font-medium">{fixedIncomeDisplayName(p)}</div>
                        <div className="text-xs text-muted-foreground">
                          {p.productName} · {p.daysSinceApplication}d
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{p.assetType}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{remunerationLabel(p)}</TableCell>
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

function SummaryCard({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <Card className={highlight ? "border-primary/40 bg-primary/5" : undefined}>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={highlight ? "text-2xl text-primary" : "text-2xl"}>{formatBRL(value)}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function fixedIncomeDisplayName(position: FixedIncomePosition): string {
  return `${position.assetType} ${position.institution} ${position.productName}`.trim();
}

function remunerationLabel(position: FixedIncomePosition): string {
  if (position.remunerationType === "PRE") {
    return `Pré ${formatPercent(position.fixedRateAnnualPercent)}% a.a.`;
  }
  return `${formatPercent(position.benchmarkPercent)}% do CDI`;
}

function formatPercent(value: number | null): string {
  if (value === null) return "0";
  return value.toFixed(2).replace(/\.?0+$/, "");
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
