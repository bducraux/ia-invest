import { useQueries, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  closePosition,
  createOperation,
  deleteOperation,
  deletePrevidenciaSnapshot,
  getPortfolioOperations,
  getPortfolios,
  getPortfolioPositions,
  getPortfolioSummary,
  updateOperation,
  updatePrevidenciaSnapshot,
  type AssetClassFilter,
  type ListOperationsParams,
  type OperationCreateInput,
  type OperationUpdateInput,
  type PrevidenciaSnapshotUpdateInput,
} from "@/lib/api";

export function usePortfolios() {
  return useQuery({
    queryKey: ["portfolios"],
    queryFn: getPortfolios,
  });
}

export function usePortfolioSummary(portfolioId: string | undefined) {
  return useQuery({
    queryKey: ["portfolio", portfolioId, "summary"],
    queryFn: () => getPortfolioSummary(portfolioId as string),
    enabled: Boolean(portfolioId),
  });
}

export function usePortfolioPositions(
  portfolioId: string | undefined,
  onlyOpen = true,
  assetClass?: AssetClassFilter,
) {
  return useQuery({
    queryKey: ["portfolio", portfolioId, "positions", onlyOpen, assetClass],
    queryFn: () => getPortfolioPositions(portfolioId as string, onlyOpen, assetClass),
    enabled: Boolean(portfolioId),
  });
}

export function usePortfolioOperations(
  portfolioId: string | undefined,
  params: ListOperationsParams = {},
) {
  return useQuery({
    queryKey: ["portfolio", portfolioId, "operations", params],
    queryFn: () => getPortfolioOperations(portfolioId as string, params),
    enabled: Boolean(portfolioId),
  });
}

export function usePortfolioSummaries(portfolioIds: string[]) {
  return useQueries({
    queries: portfolioIds.map((portfolioId) => ({
      queryKey: ["portfolio", portfolioId, "summary"],
      queryFn: () => getPortfolioSummary(portfolioId),
    })),
  });
}

export function usePortfolioPositionsList(
  portfolioIds: string[],
  onlyOpen = true,
  assetClass?: AssetClassFilter,
) {
  return useQueries({
    queries: portfolioIds.map((portfolioId) => ({
      queryKey: ["portfolio", portfolioId, "positions", onlyOpen, assetClass],
      queryFn: () => getPortfolioPositions(portfolioId, onlyOpen, assetClass),
    })),
  });
}

export function usePortfolioOperationsList(
  portfolioIds: string[],
  params: ListOperationsParams = {},
) {
  return useQueries({
    queries: portfolioIds.map((portfolioId) => ({
      queryKey: ["portfolio", portfolioId, "operations", params],
      queryFn: () => getPortfolioOperations(portfolioId, params),
    })),
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks for position lifecycle / operation CRUD / previdencia CRUD.
// All hooks invalidate the portfolio-scoped queries that may be affected.
// ---------------------------------------------------------------------------

function invalidatePortfolioCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  portfolioId: string,
): void {
  queryClient.invalidateQueries({ queryKey: ["portfolio", portfolioId] });
  queryClient.invalidateQueries({ queryKey: ["portfolios"] });
  queryClient.invalidateQueries({ queryKey: ["fixed-income"] });
}

export function useClosePosition(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetCode: string) => closePosition(portfolioId, assetCode),
    onSuccess: () => invalidatePortfolioCaches(queryClient, portfolioId),
  });
}

export function useUpdateOperation(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      operationId,
      input,
    }: {
      operationId: number;
      input: OperationUpdateInput;
    }) => updateOperation(portfolioId, operationId, input),
    onSuccess: () => invalidatePortfolioCaches(queryClient, portfolioId),
  });
}

export function useCreateOperation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      portfolioId,
      input,
    }: {
      portfolioId: string;
      input: OperationCreateInput;
    }) => createOperation(portfolioId, input),
    onSuccess: (_data, vars) =>
      invalidatePortfolioCaches(queryClient, vars.portfolioId),
  });
}

export function useDeleteOperation(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (operationId: number) =>
      deleteOperation(portfolioId, operationId),
    onSuccess: () => invalidatePortfolioCaches(queryClient, portfolioId),
  });
}

export function useUpdatePrevidenciaSnapshot(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      assetCode,
      input,
    }: {
      assetCode: string;
      input: PrevidenciaSnapshotUpdateInput;
    }) => updatePrevidenciaSnapshot(portfolioId, assetCode, input),
    onSuccess: () => invalidatePortfolioCaches(queryClient, portfolioId),
  });
}

export function useDeletePrevidenciaSnapshot(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetCode: string) =>
      deletePrevidenciaSnapshot(portfolioId, assetCode),
    onSuccess: () => invalidatePortfolioCaches(queryClient, portfolioId),
  });
}
