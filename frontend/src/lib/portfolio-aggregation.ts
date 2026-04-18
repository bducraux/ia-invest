import type {
  AllocationSlice,
  DividendEntry,
  DividendMonth,
  Operation,
  PerformancePoint,
  Portfolio,
  PortfolioSummary,
  Position,
} from "@/types/domain";
import { cents } from "@/lib/money";

type PortfolioSummaryInput = {
  portfolio: Portfolio;
  summary: PortfolioSummary;
};

export type PositionWithPortfolio = Position & {
  portfolioId: string;
  portfolioName: string;
};

export type OperationWithPortfolio = Operation & {
  portfolioId: string;
  portfolioName: string;
};

export type DividendEntryWithPortfolio = DividendEntry & {
  portfolioId: string;
  portfolioName: string;
};

export function aggregateSummaries(inputs: PortfolioSummaryInput[]): {
  summary: PortfolioSummary;
  allocationByPortfolio: AllocationSlice[];
} {
  const totalInvested = inputs.reduce((acc, item) => acc + item.summary.totalInvested, 0);
  const marketValue = inputs.reduce((acc, item) => acc + item.summary.marketValue, 0);
  const cashBalance = inputs.reduce((acc, item) => acc + item.summary.cashBalance, 0);
  const unrealizedPnl = inputs.reduce((acc, item) => acc + item.summary.unrealizedPnl, 0);
  const monthDividends = inputs.reduce((acc, item) => acc + item.summary.monthDividends, 0);

  const unrealizedPnlPct = totalInvested > 0 ? unrealizedPnl / totalInvested : 0;
  const ytdWeightedSum = inputs.reduce(
    (acc, item) => acc + item.summary.ytdReturnPct * item.summary.totalInvested,
    0,
  );
  const ytdReturnPct = totalInvested > 0 ? ytdWeightedSum / totalInvested : 0;

  const allocationMap = new Map<string, { assetClass: AllocationSlice["assetClass"]; label: string; value: number }>();
  for (const { summary } of inputs) {
    for (const slice of summary.allocation) {
      const key = slice.assetClass;
      const current = allocationMap.get(key);
      if (!current) {
        allocationMap.set(key, {
          assetClass: slice.assetClass,
          label: slice.label,
          value: slice.value,
        });
      } else {
        current.value += slice.value;
      }
    }
  }

  const allocationTotal = Array.from(allocationMap.values()).reduce((acc, slice) => acc + slice.value, 0);
  const allocation: AllocationSlice[] = Array.from(allocationMap.values())
    .map((slice) => ({
      assetClass: slice.assetClass,
      label: slice.label,
      value: cents(slice.value),
      weight: allocationTotal > 0 ? slice.value / allocationTotal : 0,
    }))
    .sort((a, b) => b.value - a.value);

  const perfMap = new Map<string, number>();
  for (const { summary } of inputs) {
    for (const point of summary.performance) {
      perfMap.set(point.date, (perfMap.get(point.date) ?? 0) + point.value);
    }
  }

  const performance: PerformancePoint[] = Array.from(perfMap.entries())
    .map(([date, value]) => ({ date, value: cents(value) }))
    .sort((a, b) => a.date.localeCompare(b.date));

  const allocationByPortfolio: AllocationSlice[] = inputs
    .map(({ portfolio, summary }) => ({
      assetClass: "CAIXA" as const,
      label: portfolio.name,
      value: cents(summary.marketValue),
      weight: marketValue > 0 ? summary.marketValue / marketValue : 0,
    }))
    .sort((a, b) => b.value - a.value);

  return {
    summary: {
      portfolioId: "all-portfolios",
      totalInvested: cents(totalInvested),
      marketValue: cents(marketValue),
      cashBalance: cents(cashBalance),
      unrealizedPnl: cents(unrealizedPnl),
      unrealizedPnlPct,
      monthDividends: cents(monthDividends),
      ytdReturnPct,
      allocation,
      performance,
    },
    allocationByPortfolio,
  };
}

export function mergePositions(
  portfolios: Portfolio[],
  positionsByPortfolio: Position[][],
): PositionWithPortfolio[] {
  return portfolios.flatMap((portfolio, index) =>
    (positionsByPortfolio[index] ?? []).map((position) => ({
      ...position,
      portfolioId: portfolio.id,
      portfolioName: portfolio.name,
    })),
  );
}

export function mergeOperations(
  portfolios: Portfolio[],
  operationsByPortfolio: Operation[][],
): OperationWithPortfolio[] {
  return portfolios
    .flatMap((portfolio, index) =>
      (operationsByPortfolio[index] ?? []).map((operation) => ({
        ...operation,
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
      })),
    )
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function toDividendEntries(operations: OperationWithPortfolio[]): DividendEntryWithPortfolio[] {
  return operations
    .filter(
      (
        operation,
      ): operation is OperationWithPortfolio & {
        type: "DIVIDENDO" | "JCP";
      } => operation.type === "DIVIDENDO" || operation.type === "JCP",
    )
    .map((operation) => ({
      id: operation.id,
      date: operation.date,
      assetCode: operation.assetCode,
      type: operation.type,
      amount: cents(operation.total),
      portfolioId: operation.portfolioId,
      portfolioName: operation.portfolioName,
    }))
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function aggregateDividendsByMonth(entries: DividendEntry[]): DividendMonth[] {
  const monthMap = new Map<string, number>();
  for (const entry of entries) {
    const monthKey = `${entry.date.slice(0, 7)}-01`;
    monthMap.set(monthKey, (monthMap.get(monthKey) ?? 0) + entry.amount);
  }

  return Array.from(monthMap.entries())
    .map(([month, amount]) => ({ month, amount: cents(amount) }))
    .sort((a, b) => a.month.localeCompare(b.month));
}