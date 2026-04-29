import type {
  DividendEntry,
  DividendMonth,
  Operation,
  Portfolio,
  PortfolioSummary,
  Position,
} from "@/types/domain";
import { cents } from "@/lib/money";

export const mockPortfolios: Portfolio[] = [
  {
    id: "p1",
    name: "Carteira Principal",
    currency: "BRL",
    allowedAssetTypes: ["stock", "fii"],
    specialization: "RENDA_VARIAVEL",
  },
  {
    id: "p2",
    name: "Renda Passiva",
    currency: "BRL",
    allowedAssetTypes: ["CDB", "LCI", "LCA"],
    specialization: "RENDA_FIXA",
  },
];

export const mockSummary: PortfolioSummary = {
  portfolioId: "p1",
  totalInvested: cents(18_540_00),
  marketValue: cents(21_873_45),
  cashBalance: cents(1_240_15),
  unrealizedPnl: cents(3_333_45),
  unrealizedPnlPct: 0.1798,
  monthDividends: cents(412_88),
  ytdReturnPct: 0.0942,
  previdenciaTotalValue: cents(0),
  allocation: [
    { assetClass: "ACAO", label: "Ações", value: cents(9_840_00), weight: 0.45 },
    { assetClass: "FII", label: "FIIs", value: cents(6_120_00), weight: 0.28 },
    { assetClass: "ETF", label: "ETFs", value: cents(2_870_00), weight: 0.13 },
    { assetClass: "RENDA_FIXA", label: "Renda Fixa", value: cents(1_803_45), weight: 0.08 },
    { assetClass: "CAIXA", label: "Caixa", value: cents(1_240_00), weight: 0.06 },
  ],
  performance: buildPerformance(),
};

function buildPerformance() {
  const points = [];
  const start = new Date("2025-05-01");
  let value = 15_200_00;
  for (let i = 0; i < 12; i++) {
    const d = new Date(start);
    d.setMonth(start.getMonth() + i);
    // Deterministic gentle climb with small dips, kept as integer cents.
    const drift = Math.round(Math.sin(i / 1.7) * 180_00) + i * 320_00;
    value = 15_200_00 + drift;
    points.push({ date: d.toISOString().slice(0, 10), value: cents(value) });
  }
  return points;
}

export const mockPositions: Position[] = [
  pos("ITSA4", "Itaúsa", "ACAO", 600, 9_50, 11_12, 0.31),
  pos("BBAS3", "Banco do Brasil", "ACAO", 200, 25_30, 28_91, 0.27),
  pos("WEGE3", "WEG", "ACAO", 80, 38_70, 41_05, 0.15),
  pos("HGLG11", "CSHG Logística", "FII", 25, 158_40, 162_85, 0.19),
  pos("MXRF11", "Maxi Renda", "FII", 600, 9_80, 9_92, 0.27),
  pos("BOVA11", "iShares Ibov", "ETF", 30, 122_10, 128_44, 0.18),
  pos("IVVB11", "iShares S&P 500", "ETF", 12, 312_00, 339_70, 0.19),
];

function pos(
  code: string,
  name: string,
  klass: Position["assetClass"],
  qty: number,
  avgC: number,
  priceC: number,
  weight: number,
): Position {
  const marketValue = qty * priceC;
  const invested = qty * avgC;
  return {
    assetCode: code,
    name,
    assetClass: klass,
    quantity: qty,
    avgPrice: cents(avgC),
    marketPrice: cents(priceC),
    marketValue: cents(marketValue),
    unrealizedPnl: cents(marketValue - invested),
    unrealizedPnlPct: (marketValue - invested) / invested,
    weight,
    quoteStatus: "live",
    quoteSource: "mock",
    quoteAgeSeconds: 0,
  };
}

export const mockOperations: Operation[] = [
  op("o1", "2026-04-12", "ITSA4", "COMPRA", 100, 11_05),
  op("o2", "2026-04-08", "HGLG11", "DIVIDENDO", 25, 1_05),
  op("o3", "2026-04-05", "BBAS3", "COMPRA", 50, 28_70),
  op("o4", "2026-03-28", "MXRF11", "DIVIDENDO", 600, 10),
  op("o5", "2026-03-22", "WEGE3", "COMPRA", 20, 40_90),
  op("o6", "2026-03-18", "IVVB11", "COMPRA", 4, 338_20),
  op("o7", "2026-03-10", "BOVA11", "VENDA", 5, 127_60),
  op("o8", "2026-03-04", "ITSA4", "DIVIDENDO", 600, 22),
  op("o9", "2026-02-26", "HGLG11", "COMPRA", 5, 160_15),
  op("o10", "2026-02-14", "BBAS3", "JCP", 200, 38),
  op("o11", "2026-02-10", "WEGE3", "COMPRA", 30, 39_10),
  op("o12", "2026-01-30", "MXRF11", "COMPRA", 200, 9_88),
];

function op(
  id: string,
  date: string,
  code: string,
  type: Operation["type"],
  qty: number,
  priceC: number,
): Operation {
  return {
    id,
    date,
    assetCode: code,
    type,
    quantity: qty,
    unitPrice: cents(priceC),
    total: cents(qty * priceC),
    source: "B3 — Sinacor",
  };
}

export const mockDividendsByMonth: DividendMonth[] = [
  { month: "2025-11-01", amount: cents(287_42) },
  { month: "2025-12-01", amount: cents(341_05) },
  { month: "2026-01-01", amount: cents(298_60) },
  { month: "2026-02-01", amount: cents(376_18) },
  { month: "2026-03-01", amount: cents(402_94) },
  { month: "2026-04-01", amount: cents(412_88) },
];

export const mockDividends: DividendEntry[] = [
  { id: "d1", date: "2026-04-08", assetCode: "HGLG11", type: "DIVIDENDO", amount: cents(26_25) },
  { id: "d2", date: "2026-03-28", assetCode: "MXRF11", type: "DIVIDENDO", amount: cents(60_00) },
  { id: "d3", date: "2026-03-04", assetCode: "ITSA4", type: "DIVIDENDO", amount: cents(132_00) },
  { id: "d4", date: "2026-02-14", assetCode: "BBAS3", type: "JCP", amount: cents(76_00) },
  { id: "d5", date: "2026-02-08", assetCode: "HGLG11", type: "DIVIDENDO", amount: cents(25_75) },
  { id: "d6", date: "2026-01-28", assetCode: "MXRF11", type: "DIVIDENDO", amount: cents(58_20) },
];
