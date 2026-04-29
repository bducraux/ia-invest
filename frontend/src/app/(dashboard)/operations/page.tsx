"use client";

import { useDeferredValue, useMemo, useState } from "react";
import Link from "next/link";
import { Pencil, Plus, Search, Trash2, Upload } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SortableHead } from "@/components/ui/sortable-head";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader } from "@/components/layout/page-header";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { formatBRL, formatQuantity } from "@/lib/money";
import { formatDate } from "@/lib/date";
import {
  deriveOwnerLabel,
  mergeOperations,
  type OperationWithPortfolio,
} from "@/lib/portfolio-aggregation";
import { OwnerPortfolioBadge } from "@/components/portfolio/owner-portfolio-badge";
import {
  useCreateOperation,
  useDeleteOperation,
  usePortfolioOperations,
  usePortfolioOperationsList,
  usePortfolios,
  useUpdateOperation,
} from "@/lib/queries";
import { useToastContext } from "@/lib/toast-context";
import type { OperationCreateInput, OperationUpdateInput } from "@/lib/api";
import {
  CreateOperationDialog,
} from "@/components/operations/create-operation-dialog";
import {
  EditOperationDialog,
  type EditableOperation,
} from "@/components/operations/edit-operation-dialog";

const OP_TYPES = ["COMPRA", "VENDA", "DIVIDENDO", "JCP", "DESDOBRAMENTO"] as const;
type OpType = (typeof OP_TYPES)[number];

type SortKey = "date" | "assetCode" | "type" | "quantity" | "unitPrice" | "total";
type SortDir = "asc" | "desc";

function sortOperations(
  list: OperationWithPortfolio[],
  key: SortKey,
  dir: SortDir,
): OperationWithPortfolio[] {
  return [...list].sort((a, b) => {
    let cmp = 0;
    if (key === "date" || key === "assetCode" || key === "type") {
      cmp = String(a[key]).localeCompare(String(b[key]));
    } else {
      cmp = (a[key] as number) - (b[key] as number);
    }
    return dir === "asc" ? cmp : -cmp;
  });
}

export default function OperationsPage() {
  const pageSize = 50;
  const scope = useDashboardScope();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"ALL" | OpType>("ALL");
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "date",
    dir: "desc",
  });
  const [pageByFilter, setPageByFilter] = useState<Record<string, number>>({});
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const portfolioIds = portfolios.map((p) => p.id);
  const activePortfolio = portfolios.find((p) => p.id === scope.portfolioId);

  const toast = useToastContext();
  const [editTarget, setEditTarget] =
    useState<(OperationWithPortfolio & { numericId: number }) | null>(null);
  const [deleteTarget, setDeleteTarget] =
    useState<(OperationWithPortfolio & { numericId: number }) | null>(null);
  const [createPortfolioId, setCreatePortfolioId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const updateMutation = useUpdateOperation(
    editTarget?.portfolioId ?? deleteTarget?.portfolioId ?? "",
  );
  const deleteMutation = useDeleteOperation(
    editTarget?.portfolioId ?? deleteTarget?.portfolioId ?? "",
  );
  const createMutation = useCreateOperation();

  function handleCreateClick() {
    if (portfolios.length === 0) {
      toast.error("Nenhuma carteira disponível.");
      return;
    }
    setCreatePortfolioId(scope.isGlobalScope ? null : (scope.portfolioId ?? null));
    setCreateOpen(true);
  }

  function handleSaveCreate(portfolioId: string, input: OperationCreateInput) {
    createMutation.mutate(
      { portfolioId, input },
      {
        onSuccess: () => {
          toast.success("Operação criada.");
          setCreateOpen(false);
          setCreatePortfolioId(null);
        },
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : "Falha ao criar operação.",
          ),
      },
    );
  }

  function asEditable(op: OperationWithPortfolio): EditableOperation | null {
    const numericId = Number(op.id);
    if (!Number.isFinite(numericId)) return null;
    return {
      id: numericId,
      portfolioId: op.portfolioId,
      date: op.date.slice(0, 10),
      assetCode: op.assetCode,
      quantity: op.quantity,
      unitPriceBrl: op.unitPrice / 100,
      totalBrl: op.total / 100,
    };
  }

  function handleSaveEdit(patch: OperationUpdateInput) {
    if (!editTarget) return;
    if (Object.keys(patch).length === 0) {
      toast.info("Nenhuma alteração para salvar.");
      setEditTarget(null);
      return;
    }
    updateMutation.mutate(
      { operationId: editTarget.numericId, input: patch },
      {
        onSuccess: () => {
          toast.success("Operação atualizada.");
          setEditTarget(null);
        },
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : "Falha ao atualizar operação.",
          ),
      },
    );
  }

  function handleConfirmDelete() {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.numericId, {
      onSuccess: () => {
        toast.success("Operação excluída.");
        setDeleteTarget(null);
      },
      onError: (err) =>
        toast.error(
          err instanceof Error ? err.message : "Falha ao excluir operação.",
        ),
    });
  }

  const scopedOperationsQuery = usePortfolioOperations(
    scope.isGlobalScope ? undefined : scope.portfolioId,
    { limit: 5000, offset: 0 },
  );
  const globalOperationsQueries = usePortfolioOperationsList(
    scope.isGlobalScope ? portfolioIds : [],
    { limit: 5000, offset: 0 },
  );

  const globalLoading = globalOperationsQueries.some((q) => q.isLoading);
  const globalError = globalOperationsQueries.find((q) => q.error)?.error;

  const isLoading = scope.isGlobalScope
    ? portfoliosQuery.isLoading || globalLoading
    : portfoliosQuery.isLoading || scopedOperationsQuery.isLoading;
  const error = scope.isGlobalScope
    ? portfoliosQuery.error || globalError
    : portfoliosQuery.error || scopedOperationsQuery.error;

  const operations: OperationWithPortfolio[] = scope.isGlobalScope
    ? mergeOperations(
        portfolios,
        globalOperationsQueries.map((q) => q.data?.operations ?? []),
      )
    : (scopedOperationsQuery.data?.operations ?? []).map((operation) => ({
        ...operation,
        portfolioId: activePortfolio?.id ?? "",
        portfolioName: activePortfolio?.name ?? "Carteira",
        ...deriveOwnerLabel(activePortfolio),
      }));

  const filteredOperations = useMemo(() => {
    let result = operations;

    if (typeFilter !== "ALL") {
      result = result.filter((op) => op.type === typeFilter);
    }

    if (deferredSearch) {
      result = result.filter((op) =>
        [op.assetCode, op.type, op.source, op.portfolioName]
          .join(" ")
          .toLowerCase()
          .includes(deferredSearch),
      );
    }

    return sortOperations(result, sort.key, sort.dir);
  }, [operations, typeFilter, deferredSearch, sort]);

  function handleSort(key: string) {
    const typed = key as SortKey;
    setSort((prev) =>
      prev.key === typed
        ? { key: typed, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key: typed, dir: "desc" },
    );
  }

  const paginationKey = [
    scope.isGlobalScope ? "global" : scope.portfolioId ?? "",
    deferredSearch,
    typeFilter,
    sort.key,
    sort.dir,
  ].join("|");
  const requestedPage = pageByFilter[paginationKey] ?? 1;

  const totalPages = Math.max(1, Math.ceil(filteredOperations.length / pageSize));
  const currentPage = Math.min(requestedPage, totalPages);
  const paginatedOperations = filteredOperations.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  if (isLoading) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader title="Histórico de operações" description="Carregando dados do backend..." />
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Histórico de operações"
            description="Falha ao carregar operações. Verifique se a API está rodando."
          />
        </main>
      </>
    );
  }

  if (!scope.isGlobalScope && !activePortfolio) {
    return (
      <>
        <TopBar title="Operações" />
        <main className="flex-1 space-y-6 p-4 md:p-6">
          <PageHeader
            title="Histórico de operações"
            description="Selecione uma carteira válida na navegação lateral."
          />
        </main>
      </>
    );
  }

  const total = scope.isGlobalScope
    ? globalOperationsQueries.reduce((acc, q) => acc + (q.data?.total ?? 0), 0)
    : scopedOperationsQuery.data?.total ?? 0;

  const title = scope.isGlobalScope
    ? "Histórico de operações consolidado"
    : `Histórico de operações - ${activePortfolio?.name}`;
  const description = scope.isGlobalScope
    ? "Compras, vendas e proventos importados de todas as carteiras."
    : `Compras, vendas e proventos importados da carteira ${activePortfolio?.name}.`;

  const hasFilters = deferredSearch || typeFilter !== "ALL";

  return (
    <>
      <TopBar title="Operações" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title={title}
          description={description}
          actions={
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={handleCreateClick}
                title="Criar nova operação manual"
              >
                <Plus className="h-4 w-4" />
                Nova operação
              </Button>
              <Link
                href="/import"
                className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-transparent px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <Upload className="h-4 w-4" />
                Importar
              </Link>
            </div>
          }
        />

        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle className="text-base text-foreground">
                  {filteredOperations.length} operação
                  {filteredOperations.length === 1 ? "" : "ões"}
                </CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {hasFilters ? `Filtradas de ${total} no total.` : `${total} no total.`}
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as "ALL" | OpType)}
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="ALL">Todos os tipos</option>
                  {OP_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <div className="relative w-full sm:w-64">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar ativo, tipo ou origem"
                    className="pl-9"
                  />
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead col="date" sortKey={sort.key} direction={sort.dir} onSort={handleSort}>
                    Data
                  </SortableHead>
                  {scope.isGlobalScope ? <TableHead>Carteira</TableHead> : null}
                  <SortableHead col="assetCode" sortKey={sort.key} direction={sort.dir} onSort={handleSort}>
                    Ativo
                  </SortableHead>
                  <SortableHead col="type" sortKey={sort.key} direction={sort.dir} onSort={handleSort}>
                    Tipo
                  </SortableHead>
                  <SortableHead col="quantity" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Qtd.
                  </SortableHead>
                  <SortableHead col="unitPrice" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Preço unit.
                  </SortableHead>
                  <SortableHead col="total" sortKey={sort.key} direction={sort.dir} onSort={handleSort} className="text-right">
                    Total
                  </SortableHead>
                  <TableHead>Origem</TableHead>
                  <TableHead className="w-24 text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedOperations.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={scope.isGlobalScope ? 9 : 8}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      Nenhuma operação encontrada para o filtro atual.
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedOperations.map((op) => (
                    <TableRow key={`${op.portfolioId}-${op.id}`}>
                      <TableCell>{formatDate(op.date)}</TableCell>
                      {scope.isGlobalScope ? (
                        <TableCell>
                          <OwnerPortfolioBadge
                            portfolioName={op.portfolioName}
                            ownerName={op.ownerName}
                          />
                        </TableCell>
                      ) : null}
                      <TableCell className="font-medium">{op.assetCode}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            op.type === "COMPRA"
                              ? "positive"
                              : op.type === "VENDA"
                                ? "negative"
                                : "muted"
                          }
                        >
                          {op.type}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">{formatQuantity(op.quantity)}</TableCell>
                      <TableCell className="text-right">{formatBRL(op.unitPrice)}</TableCell>
                      <TableCell className="text-right font-medium">
                        {formatBRL(op.total)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{op.source}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Editar operação ${op.id}`}
                            title="Editar operação"
                            onClick={() => {
                              const numericId = Number(op.id);
                              if (!Number.isFinite(numericId)) return;
                              setEditTarget({ ...op, numericId });
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Excluir operação ${op.id}`}
                            title="Excluir operação"
                            onClick={() => {
                              const numericId = Number(op.id);
                              if (!Number.isFinite(numericId)) return;
                              setDeleteTarget({ ...op, numericId });
                            }}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
            <div className="flex flex-col gap-3 border-t border-border px-4 py-4 md:flex-row md:items-center md:justify-between">
              <p className="text-sm text-muted-foreground">
                Página {currentPage} de {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPageByFilter((prev) => ({
                      ...prev,
                      [paginationKey]: Math.max(1, currentPage - 1),
                    }))
                  }
                  disabled={currentPage <= 1}
                >
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPageByFilter((prev) => ({
                      ...prev,
                      [paginationKey]: Math.min(totalPages, currentPage + 1),
                    }))
                  }
                  disabled={currentPage >= totalPages}
                >
                  Próxima
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>
      <CreateOperationDialog
        open={createOpen}
        portfolios={portfolios}
        defaultPortfolioId={createPortfolioId}
        busy={createMutation.isPending}
        onCancel={() => {
          setCreateOpen(false);
          setCreatePortfolioId(null);
        }}
        onSave={handleSaveCreate}
      />
      <EditOperationDialog
        open={editTarget !== null}
        operation={editTarget ? asEditable(editTarget) : null}
        busy={updateMutation.isPending}
        onCancel={() => setEditTarget(null)}
        onSave={handleSaveEdit}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir operação"
        description={
          deleteTarget
            ? `Tem certeza que deseja excluir a operação de ${deleteTarget.assetCode} de ${deleteTarget.date.slice(0, 10)}? A posição do ativo será recalculada automaticamente.`
            : ""
        }
        confirmLabel="Excluir"
        destructive
        busy={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
}
