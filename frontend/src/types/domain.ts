import type { Cents } from "@/lib/money";

export type PortfolioSpecialization =
  | "GENERIC"
  | "RENDA_FIXA"
  | "RENDA_VARIAVEL"
  | "CRIPTO"
  | "PREVIDENCIA";

export type AssetClass =
  | "ACAO"
  | "FII"
  | "ETF"
  | "RENDA_FIXA"
  | "PREVIDENCIA"
  | "CAIXA"
  | "CRIPTO";

export type OperationType = "COMPRA" | "VENDA" | "DIVIDENDO" | "JCP" | "DESDOBRAMENTO";

export interface Portfolio {
  id: string;
  name: string;
  currency: "BRL";
  allowedAssetTypes: string[];
  specialization: PortfolioSpecialization;
}

export interface PortfolioSummary {
  portfolioId: string;
  totalInvested: Cents;
  marketValue: Cents;
  cashBalance: Cents;
  unrealizedPnl: Cents;
  unrealizedPnlPct: number; // 0.1234 = +12,34%
  monthDividends: Cents;
  ytdReturnPct: number;
  previdenciaTotalValue: Cents;
  allocation: AllocationSlice[];
  performance: PerformancePoint[];
}

export interface AllocationSlice {
  assetClass: AssetClass;
  label: string;
  value: Cents;
  weight: number; // 0..1
}

export interface PerformancePoint {
  date: string; // ISO
  value: Cents;
}

export interface Position {
  assetCode: string;
  name: string;
  assetClass: AssetClass;
  quantity: number;
  avgPrice: Cents;
  marketPrice: Cents;
  marketValue: Cents;
  unrealizedPnl: Cents;
  unrealizedPnlPct: number;
  weight: number;
  quoteStatus: "live" | "cache_fresh" | "cache_stale" | "avg_fallback";
  quoteSource: string;
  quoteAgeSeconds?: number | null;
}

export interface Operation {
  id: string;
  date: string; // ISO
  assetCode: string;
  type: OperationType;
  quantity: number;
  unitPrice: Cents;
  total: Cents;
  source: string;
}

export interface DividendMonth {
  month: string; // YYYY-MM-01 ISO
  amount: Cents;
}

export interface DividendEntry {
  id: string;
  date: string;
  assetCode: string;
  type: "DIVIDENDO" | "JCP";
  amount: Cents;
}
