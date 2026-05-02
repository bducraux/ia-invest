import type {
  Member,
  Operation,
  Portfolio,
  PortfolioSummary,
  Position,
} from "@/types/domain";

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

export function getPortfolios(ownerId?: string): Promise<Portfolio[]> {
  const query = toQueryString({ ownerId });
  return apiFetch<Portfolio[]>(`/api/portfolios${query}`);
}

export function getPortfolioSummary(portfolioId: string): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>(`/api/portfolios/${portfolioId}/summary`);
}

export interface EquityCurveQuery {
  from?: string;
  to?: string;
  periodMonths?: number;
}

export interface EquityCurveRawPoint {
  month: string;
  as_of_date: string;
  market_value_cents: number;
  breakdown_by_class: Record<string, number>;
  net_contributions_cents: number;
  cumulative_contributions_cents: number;
  dividends_received_cents: number;
  warnings: string[];
}

export interface EquityCurveRaw {
  portfolio_ids: string[];
  from_month: string | null;
  to_month: string | null;
  series: EquityCurveRawPoint[];
  generated_at: string;
}

function buildEquityCurveQuery(params: EquityCurveQuery = {}): string {
  return toQueryString({
    from: params.from,
    to: params.to,
    period_months: params.periodMonths,
  });
}

export function getEquityCurve(
  portfolioId: string | null,
  params: EquityCurveQuery = {},
): Promise<EquityCurveRaw> {
  const query = buildEquityCurveQuery(params);
  const path =
    portfolioId === null
      ? `/api/equity-curve${query}`
      : `/api/portfolios/${portfolioId}/equity-curve${query}`;
  return apiFetch<EquityCurveRaw>(path);
}

// ---------------------------------------------------------------------------
// IRPF report (DIRPF — Bens e Direitos + Rendimentos)
// ---------------------------------------------------------------------------

export type IrpfSectionCategory = "isento" | "exclusivo" | "bem_direito";

export interface IrpfBemDireitoExtra {
  quantity: number;
  avg_price_cents: number;
  total_cents: number;
  previous_total_cents: number;
  previous_quantity: number;
}

export interface IrpfRow {
  asset_code: string;
  asset_name: string | null;
  cnpj: string | null;
  value_cents: number;
  extra: IrpfBemDireitoExtra | null;
  discriminacao: string | null;
  warnings: string[];
}

export interface IrpfSection {
  code: string;
  title: string;
  category: IrpfSectionCategory;
  total_cents: number;
  rows: IrpfRow[];
}

export interface IrpfReport {
  portfolio_id: string;
  base_year: number;
  generated_at: string;
  warnings: string[];
  sections: IrpfSection[];
}

export function getIrpfReport(
  portfolioId: string,
  year: number,
): Promise<IrpfReport> {
  return apiFetch<IrpfReport>(
    `/api/portfolios/${portfolioId}/irpf?year=${year}`,
  );
}

export type AssetClass =
  | "acao"
  | "fii"
  | "fiagro"
  | "bdr"
  | "etf"
  | "cripto"
  | "stocks";

export interface AssetMetadata {
  assetCode: string;
  cnpj: string | null;
  assetClass: AssetClass;
  assetNameOficial: string | null;
  sectorCategory: string | null;
  sectorSubcategory: string | null;
  siteRi: string | null;
  source: string;
  notes: string | null;
  dataSource: string | null;
  lastSyncedAt: string | null;
}

export async function updatePortfolioName(
  portfolioId: string,
  payload: { name: string; ownerId?: string },
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

export function transferPortfolioOwner(
  portfolioId: string,
  newOwnerId: string,
): Promise<Portfolio> {
  return apiPostJson<Portfolio>(
    `/api/portfolios/${portfolioId}/transfer-owner`,
    { newOwnerId },
  );
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

export interface PortfolioExportFile {
  kind: string;
  path: string;
  rows: number;
}

export interface PortfolioExportResponse {
  portfolioId: string;
  outputDir: string;
  totalFiles: number;
  files: PortfolioExportFile[];
}

export function exportPortfolio(
  portfolioId: string,
): Promise<PortfolioExportResponse> {
  return apiPost<PortfolioExportResponse>(
    `/api/portfolios/${portfolioId}/export`,
  );
}

export interface BenchmarkCoverage {
  benchmark: string;
  coverageStart: string | null;
  coverageEnd: string | null;
  rowCount: number;
  lastFetchedAt: string | null;
}

export interface BenchmarkSyncResult {
  benchmark: string;
  rowsInserted: number;
  coverageStart: string | null;
  coverageEnd: string | null;
  source: string;
  lastFetchedAt: string | null;
}

export interface BenchmarkSyncRequest {
  startDate?: string;
  endDate?: string;
  fullRefresh?: boolean;
}

export function getBenchmarkCoverage(benchmark: string): Promise<BenchmarkCoverage> {
  return apiFetch<BenchmarkCoverage>(`/api/benchmarks/${benchmark}/coverage`);
}

export function syncBenchmark(
  benchmark: string,
  payload: BenchmarkSyncRequest = {},
): Promise<BenchmarkSyncResult> {
  return apiPostJson<BenchmarkSyncResult>(`/api/benchmarks/${benchmark}/sync`, payload);
}

// --- FX rates (PTAX) ---------------------------------------------------------

export interface FxCoverage {
  pair: string;
  coverageStart: string | null;
  coverageEnd: string | null;
  rowCount: number;
  lastFetchedAt: string | null;
}

export interface FxSyncResult {
  pair: string;
  rowsInserted: number;
  coverageStart: string | null;
  coverageEnd: string | null;
  source: string;
  lastFetchedAt: string | null;
}

export interface FxSyncRequest {
  startDate?: string;
  endDate?: string;
  fullRefresh?: boolean;
}

export function getFxCoverage(pair: string): Promise<FxCoverage> {
  return apiFetch<FxCoverage>(`/api/fx/${pair}/coverage`);
}

export function syncFx(
  pair: string,
  payload: FxSyncRequest = {},
): Promise<FxSyncResult> {
  return apiPostJson<FxSyncResult>(`/api/fx/${pair}/sync`, payload);
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

// ---------------------------------------------------------------------------
// Position lifecycle (event-sourced portfolios) and operations CRUD
// ---------------------------------------------------------------------------

export interface OperationUpdateInput {
  assetCode?: string;
  assetName?: string | null;
  assetType?: string;
  operationType?: string;
  operationDate?: string;
  settlementDate?: string | null;
  quantity?: number;
  unitPrice?: number;
  grossValue?: number;
  fees?: number;
  netValue?: number;
  notes?: string | null;
  broker?: string | null;
  account?: string | null;
}

async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
}

export async function closePosition(
  portfolioId: string,
  assetCode: string,
): Promise<void> {
  return apiDelete(
    `/api/portfolios/${portfolioId}/positions/${encodeURIComponent(assetCode)}`,
  );
}

export async function updateOperation(
  portfolioId: string,
  operationId: number,
  input: OperationUpdateInput,
): Promise<Record<string, unknown>> {
  return apiPatch<Record<string, unknown>>(
    `/api/portfolios/${portfolioId}/operations/${operationId}`,
    input,
  );
}

export interface OperationCreateInput {
  assetCode: string;
  assetType: string;
  operationType: string;
  operationDate: string;
  quantity: number;
  unitPrice: number;
  grossValue: number;
  assetName?: string | null;
  settlementDate?: string | null;
  fees?: number;
  netValue?: number;
  notes?: string | null;
  broker?: string | null;
  account?: string | null;
}

export async function createOperation(
  portfolioId: string,
  input: OperationCreateInput,
): Promise<Record<string, unknown>> {
  return apiPostJson<Record<string, unknown>>(
    `/api/portfolios/${portfolioId}/operations`,
    input,
  );
}

export async function deleteOperation(
  portfolioId: string,
  operationId: number,
): Promise<void> {
  return apiDelete(`/api/portfolios/${portfolioId}/operations/${operationId}`);
}

export interface PrevidenciaSnapshotUpdateInput {
  productName?: string;
  quantity?: number;
  unitPriceCents?: number;
  marketValueCents?: number;
  periodMonth?: string;
  periodStartDate?: string;
  periodEndDate?: string;
}

export async function updatePrevidenciaSnapshot(
  portfolioId: string,
  assetCode: string,
  input: PrevidenciaSnapshotUpdateInput,
): Promise<Record<string, unknown>> {
  return apiPatch<Record<string, unknown>>(
    `/api/portfolios/${portfolioId}/previdencia/${encodeURIComponent(assetCode)}`,
    input,
  );
}

export async function deletePrevidenciaSnapshot(
  portfolioId: string,
  assetCode: string,
): Promise<void> {
  return apiDelete(
    `/api/portfolios/${portfolioId}/previdencia/${encodeURIComponent(assetCode)}`,
  );
}

export interface PrevidenciaHistorySnapshot {
  id: number | null;
  assetCode: string;
  productName: string;
  periodMonth: string;
  periodStartDate: string | null;
  periodEndDate: string | null;
  quantity: number;
  unitPriceCents: number;
  marketValueCents: number;
  sourceFile: string | null;
}

export interface PrevidenciaHistory {
  portfolioId: string;
  assetCode: string | null;
  snapshots: PrevidenciaHistorySnapshot[];
}

export async function getPrevidenciaHistory(
  portfolioId: string,
  assetCode?: string,
): Promise<PrevidenciaHistory> {
  const qs = assetCode ? `?asset_code=${encodeURIComponent(assetCode)}` : "";
  return apiFetch<PrevidenciaHistory>(
    `/api/portfolios/${portfolioId}/previdencia/history${qs}`,
  );
}

// --- Members ----------------------------------------------------------------

export interface MemberSummary {
  member: Member;
  portfolios: Array<{
    id: string;
    name: string;
    open_positions: number;
    total_cost_cents: number;
    realized_pnl_cents: number;
    dividends_cents: number;
  }>;
  totals: {
    open_positions: number;
    total_cost_cents: number;
    realized_pnl_cents: number;
    dividends_cents: number;
  };
}

export interface MemberCreateInput {
  id: string;
  name: string;
  displayName?: string;
  email?: string;
}

export interface MemberUpdateInput {
  name?: string;
  displayName?: string | null;
  email?: string | null;
  status?: "active" | "inactive";
}

export function getMembers(status?: "active" | "inactive"): Promise<Member[]> {
  const query = toQueryString({ status });
  return apiFetch<Member[]>(`/api/members${query}`);
}

export function getMember(memberId: string): Promise<Member> {
  return apiFetch<Member>(`/api/members/${encodeURIComponent(memberId)}`);
}

export function getMemberPortfolios(memberId: string): Promise<Portfolio[]> {
  return apiFetch<Portfolio[]>(
    `/api/members/${encodeURIComponent(memberId)}/portfolios`,
  );
}

export function getMemberSummary(memberId: string): Promise<MemberSummary> {
  return apiFetch<MemberSummary>(
    `/api/members/${encodeURIComponent(memberId)}/summary`,
  );
}

export function createMember(input: MemberCreateInput): Promise<Member> {
  return apiPostJson<Member>("/api/members", input);
}

export function updateMember(
  memberId: string,
  input: MemberUpdateInput,
): Promise<Member> {
  return apiPatch<Member>(
    `/api/members/${encodeURIComponent(memberId)}`,
    input,
  );
}

export function deleteMember(memberId: string): Promise<void> {
  return apiDelete(`/api/members/${encodeURIComponent(memberId)}`);
}
