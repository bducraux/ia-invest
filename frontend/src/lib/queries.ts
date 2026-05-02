import { useQueries, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  closePosition,
  createOperation,
  deleteOperation,
  deletePrevidenciaSnapshot,
  getEquityCurve,
  getIrpfReport,
  getPortfolioOperations,
  getPortfolios,
  getPortfolioPositions,
  getPortfolioSummary,
  getPrevidenciaHistory,
  updateOperation,
  updatePrevidenciaSnapshot,
  type AssetClassFilter,
  type EquityCurveQuery,
  type EquityCurveRaw,
  type ListOperationsParams,
  type OperationCreateInput,
  type OperationUpdateInput,
  type PrevidenciaHistory,
  type PrevidenciaSnapshotUpdateInput,
} from "@/lib/api";
import type { EquityCurve, EquityCurvePoint } from "@/types/domain";
import type { Cents } from "@/lib/money";

export function usePortfolios() {
  return useQuery({
    queryKey: ["portfolios"],
    queryFn: () => getPortfolios(),
  });
}

export function useIrpfReport(
  portfolioId: string | undefined,
  year: number | undefined,
) {
  return useQuery({
    queryKey: ["portfolio", portfolioId, "irpf", year],
    queryFn: () => getIrpfReport(portfolioId as string, year as number),
    enabled: Boolean(portfolioId) && Boolean(year),
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

export function usePrevidenciaHistory(
  portfolioId: string | null | undefined,
  assetCode?: string,
) {
  return useQuery<PrevidenciaHistory>({
    queryKey: ["previdencia-history", portfolioId ?? null, assetCode ?? null],
    queryFn: () => getPrevidenciaHistory(portfolioId as string, assetCode),
    enabled: Boolean(portfolioId),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Equity curve (evolução patrimonial mensal)
// ---------------------------------------------------------------------------

function mapEquityCurve(raw: EquityCurveRaw): EquityCurve {
  return {
    portfolioIds: raw.portfolio_ids,
    fromMonth: raw.from_month,
    toMonth: raw.to_month,
    generatedAt: raw.generated_at,
    series: raw.series.map<EquityCurvePoint>((p) => ({
      month: p.month,
      asOfDate: p.as_of_date,
      marketValue: p.market_value_cents as Cents,
      breakdownByClass: Object.fromEntries(
        Object.entries(p.breakdown_by_class).map(([k, v]) => [k, v as Cents]),
      ),
      netContributions: p.net_contributions_cents as Cents,
      cumulativeContributions: p.cumulative_contributions_cents as Cents,
      dividendsReceived: p.dividends_received_cents as Cents,
      warnings: p.warnings,
    })),
  };
}

export function useEquityCurve(
  portfolioId: string | null,
  params: EquityCurveQuery = {},
) {
  return useQuery({
    queryKey: ["equity-curve", portfolioId ?? "__all__", params],
    queryFn: async () => mapEquityCurve(await getEquityCurve(portfolioId, params)),
  });
}

// ---------------------------------------------------------------------------
// Members
// ---------------------------------------------------------------------------

import {
  createMember,
  deleteMember,
  getMember,
  getMemberPortfolios,
  getMemberSummary,
  getMembers,
  transferPortfolioOwner,
  updateMember,
  type MemberCreateInput,
  type MemberUpdateInput,
} from "@/lib/api";

export function useMembers(status?: "active" | "inactive") {
  return useQuery({
    queryKey: ["members", status ?? "all"],
    queryFn: () => getMembers(status),
  });
}

export function useMember(memberId: string | undefined) {
  return useQuery({
    queryKey: ["member", memberId],
    queryFn: () => getMember(memberId as string),
    enabled: Boolean(memberId),
  });
}

export function useMemberPortfolios(memberId: string | undefined) {
  return useQuery({
    queryKey: ["member", memberId, "portfolios"],
    queryFn: () => getMemberPortfolios(memberId as string),
    enabled: Boolean(memberId),
  });
}

export function useMemberSummary(memberId: string | undefined) {
  return useQuery({
    queryKey: ["member", memberId, "summary"],
    queryFn: () => getMemberSummary(memberId as string),
    enabled: Boolean(memberId),
  });
}

export function useCreateMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MemberCreateInput) => createMember(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
  });
}

export function useUpdateMember(memberId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MemberUpdateInput) => updateMember(memberId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
      queryClient.invalidateQueries({ queryKey: ["member", memberId] });
    },
  });
}

export function useDeleteMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => deleteMember(memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
  });
}

export function useTransferPortfolioOwner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      portfolioId,
      newOwnerId,
    }: {
      portfolioId: string;
      newOwnerId: string;
    }) => transferPortfolioOwner(portfolioId, newOwnerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
  });
}
