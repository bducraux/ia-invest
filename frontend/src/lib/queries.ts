import { useQueries, useQuery } from "@tanstack/react-query";

import {
  getPortfolioOperations,
  getPortfolios,
  getPortfolioPositions,
  getPortfolioSummary,
  type AssetClassFilter,
  type ListOperationsParams,
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
