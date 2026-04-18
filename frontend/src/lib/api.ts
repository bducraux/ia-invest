import type { Operation, Portfolio, PortfolioSummary, Position } from "@/types/domain";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ListOperationsParams {
  assetCode?: string;
  operationType?: Operation["type"];
  startDate?: string;
  endDate?: string;
  limit?: number;
  offset?: number;
}

export interface ListOperationsResponse {
  operations: Operation[];
  total: number;
  limit: number;
  offset: number;
}

export interface QuoteRefreshResponse {
  scope: "global" | "portfolio";
  portfolios: string[];
  totalAssets: number;
  liveCount: number;
  cacheFreshCount: number;
  cacheStaleCount: number;
  avgFallbackCount: number;
  failedCount: number;
}

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return (await response.json()) as T;
}

async function apiPost<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return (await response.json()) as T;
}

function toQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      query.set(key, String(value));
    }
  }
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

export function getPortfolios(): Promise<Portfolio[]> {
  return apiFetch<Portfolio[]>("/api/portfolios");
}

export function getPortfolioSummary(portfolioId: string): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>(`/api/portfolios/${portfolioId}/summary`);
}

export async function getPortfolioPositions(
  portfolioId: string,
  onlyOpen = true,
): Promise<Position[]> {
  const query = toQueryString({ onlyOpen });
  const response = await apiFetch<{ positions: Position[] }>(
    `/api/portfolios/${portfolioId}/positions${query}`,
  );
  return response.positions;
}

export function getPortfolioOperations(
  portfolioId: string,
  params: ListOperationsParams = {},
): Promise<ListOperationsResponse> {
  const query = toQueryString({
    assetCode: params.assetCode,
    operationType: params.operationType,
    startDate: params.startDate,
    endDate: params.endDate,
    limit: params.limit,
    offset: params.offset,
  });
  return apiFetch<ListOperationsResponse>(`/api/portfolios/${portfolioId}/operations${query}`);
}

export function refreshQuotes(portfolioId?: string): Promise<QuoteRefreshResponse> {
  if (portfolioId) {
    return apiPost<QuoteRefreshResponse>(`/api/portfolios/${portfolioId}/quotes/refresh`);
  }
  return apiPost<QuoteRefreshResponse>("/api/quotes/refresh");
}
