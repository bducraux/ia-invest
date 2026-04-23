import type { Operation, Portfolio, PortfolioSummary, Position } from "@/types/domain";

export type AssetClassFilter = Position["assetClass"] | "RENDA_VARIAVEL";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export interface ListOperationsParams {
  assetCode?: string;
  assetClass?: AssetClassFilter;
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

export interface AppSettings {
  cdiAnnualRate: number | null;
  selicAnnualRate: number | null;
  ipcaAnnualRate: number | null;
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

async function apiPatch<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return (await response.json()) as T;
}

async function apiPostJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
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

export async function updatePortfolioName(
  portfolioId: string,
  payload: { name: string },
): Promise<Portfolio> {
  const response = await fetch(`${API_BASE}/api/portfolios/${portfolioId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as Portfolio;
}

export async function getPortfolioPositions(
  portfolioId: string,
  onlyOpen = true,
  assetClass?: AssetClassFilter,
): Promise<Position[]> {
  const query = toQueryString({ onlyOpen, assetClass });
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
    assetClass: params.assetClass,
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

export function getAppSettings(): Promise<AppSettings> {
  return apiFetch<AppSettings>("/api/settings");
}

export async function updateAppSettings(payload: Partial<AppSettings>): Promise<AppSettings> {
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as AppSettings;
}

/**
 * Calculate daily rate from annual rate percentage using the formula:
 * daily = (1 + annualPct/100)^(1/252) - 1
 * where 252 is the number of business days per year.
 * @param annualPct - annual rate as percentage (e.g. 14.65 for 14.65%)
 */
export function calculateDailyRateFromAnnual(annualPct: number): number {
  return Math.pow(1 + annualPct / 100, 1 / 252) - 1;
}

// --- Fixed income (renda fixa) -----------------------------------------------

export interface FixedIncomePosition {
  id: number;
  institution: string;
  assetType: "CDB" | "LCI" | "LCA";
  productName: string;
  remunerationType: "PRE" | "CDI_PERCENT";
  benchmark: "NONE" | "CDI";
  investorType: string;
  currency: string;
  applicationDate: string;
  maturityDate: string;
  liquidityLabel: string | null;
  principalAppliedBrl: number;     // cents
  fixedRateAnnualPercent: number | null;
  benchmarkPercent: number | null;
  grossValueCurrentBrl: number;    // cents
  grossIncomeCurrentBrl: number;   // cents
  estimatedIrCurrentBrl: number;   // cents
  netValueCurrentBrl: number;      // cents
  taxBracketCurrent: string | null;
  daysSinceApplication: number;
  valuationDate: string;
  isComplete: boolean;
  incompleteReason: string | null;
  status: string;
  autoReapplyEnabled: boolean;
  isMatured: boolean;
  notes: string | null;
}

export interface FixedIncomeImportResponse {
  imported: number;
  failed: number;
  positions: FixedIncomePosition[];
  errors: { rowIndex: number | null; message: string; field: string | null }[];
}

export interface CreateFixedIncomeInput {
  institution: string;
  assetType: "CDB" | "LCI" | "LCA";
  productName: string;
  remunerationType: "PRE" | "CDI_PERCENT";
  benchmark?: "NONE" | "CDI";
  applicationDate: string;
  maturityDate: string;
  principalAppliedBrl: number;
  fixedRateAnnualPercent?: number | null;
  benchmarkPercent?: number | null;
  liquidityLabel?: string | null;
  notes?: string | null;
  autoReapplyEnabled?: boolean;
}

export interface UpdateFixedIncomeInput {
  institution?: string;
  assetType?: "CDB" | "LCI" | "LCA";
  productName?: string;
  remunerationType?: "PRE" | "CDI_PERCENT";
  benchmark?: "NONE" | "CDI";
  applicationDate?: string;
  maturityDate?: string;
  principalAppliedBrl?: number;
  fixedRateAnnualPercent?: number | null;
  benchmarkPercent?: number | null;
  liquidityLabel?: string | null;
  notes?: string | null;
}

export async function getFixedIncomePositions(
  portfolioId: string,
): Promise<FixedIncomePosition[]> {
  const response = await apiFetch<{ positions: FixedIncomePosition[] }>(
    `/api/portfolios/${portfolioId}/fixed-income`,
  );
  return response.positions;
}

export async function createFixedIncomePosition(
  portfolioId: string,
  input: CreateFixedIncomeInput,
): Promise<FixedIncomePosition> {
  const response = await fetch(
    `${API_BASE}/api/portfolios/${portfolioId}/fixed-income`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as FixedIncomePosition;
}

export async function importFixedIncomeCSV(
  portfolioId: string,
  file: File,
): Promise<FixedIncomeImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    `${API_BASE}/api/portfolios/${portfolioId}/fixed-income/import-csv`,
    { method: "POST", body: form },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as FixedIncomeImportResponse;
}

export async function updateFixedIncomePosition(
  portfolioId: string,
  positionId: number,
  input: UpdateFixedIncomeInput,
): Promise<FixedIncomePosition> {
  return apiPatch<FixedIncomePosition>(
    `/api/portfolios/${portfolioId}/fixed-income/${positionId}`,
    input,
  );
}

export async function closeFixedIncomePosition(
  portfolioId: string,
  positionId: number,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/portfolios/${portfolioId}/fixed-income/${positionId}`,
    { method: "DELETE", headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
}

export async function redeemFixedIncomePosition(
  portfolioId: string,
  positionId: number,
  asOfDate?: string,
): Promise<FixedIncomePosition> {
  return apiPostJson<FixedIncomePosition>(
    `/api/portfolios/${portfolioId}/fixed-income/${positionId}/redeem`,
    { asOfDate: asOfDate ?? null },
  );
}

export async function setFixedIncomeAutoReapply(
  portfolioId: string,
  positionId: number,
  enabled: boolean,
): Promise<FixedIncomePosition> {
  return apiPatch<FixedIncomePosition>(
    `/api/portfolios/${portfolioId}/fixed-income/${positionId}/auto-reapply`,
    { enabled },
  );
}
