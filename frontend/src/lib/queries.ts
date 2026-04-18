import { useQuery } from "@tanstack/react-query";

import {
  getPortfolioOperations,
  getPortfolios,
  getPortfolioPositions,
  getPortfolioSummary,
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

export function usePortfolioPositions(portfolioId: string | undefined, onlyOpen = true) {
  return useQuery({
    queryKey: ["portfolio", portfolioId, "positions", onlyOpen],
    queryFn: () => getPortfolioPositions(portfolioId as string, onlyOpen),
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
