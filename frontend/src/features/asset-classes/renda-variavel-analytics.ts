import { cents } from "@/lib/money";
import type { PositionWithPortfolio } from "@/lib/portfolio-aggregation";
import type { AllocationSlice } from "@/types/domain";

export interface AssetExposure {
  assetCode: string;
  name: string;
  marketValue: number;
  quantity: number;
  portfolioCount: number;
  weight: number;
}

const ASSET_CLASS_LABELS: Record<string, string> = {
  ACAO: "Ações",
  FII: "FIIs",
  ETF: "ETFs",
};

export function buildRendaVariavelTypeSlices(
  positions: PositionWithPortfolio[],
): AllocationSlice[] {
  const validPositions = positions.filter((position) =>
    position.assetClass === "ACAO"
    || position.assetClass === "FII"
    || position.assetClass === "ETF",
  );
  const total = validPositions.reduce((sum, position) => sum + position.marketValue, 0);
  const groups = new Map<string, number>();

  for (const position of validPositions) {
    groups.set(position.assetClass, (groups.get(position.assetClass) ?? 0) + position.marketValue);
  }

  return Array.from(groups.entries())
    .map(([assetClass, value]) => ({
      assetClass: assetClass as AllocationSlice["assetClass"],
      label: ASSET_CLASS_LABELS[assetClass] ?? assetClass,
      value: cents(value),
      weight: total > 0 ? value / total : 0,
    }))
    .sort((left, right) => right.value - left.value);
}

export function aggregateRendaVariavelExposure(
  positions: PositionWithPortfolio[],
): AssetExposure[] {
  const total = positions.reduce((sum, position) => sum + position.marketValue, 0);
  const grouped = new Map<string, {
    assetCode: string;
    name: string;
    marketValue: number;
    quantity: number;
    portfolios: Set<string>;
  }>();

  for (const position of positions) {
    const current = grouped.get(position.assetCode);
    if (!current) {
      grouped.set(position.assetCode, {
        assetCode: position.assetCode,
        name: position.name,
        marketValue: position.marketValue,
        quantity: position.quantity,
        portfolios: new Set([position.portfolioId]),
      });
      continue;
    }

    current.marketValue += position.marketValue;
    current.quantity += position.quantity;
    current.portfolios.add(position.portfolioId);
    if (current.name === current.assetCode && position.name !== position.assetCode) {
      current.name = position.name;
    }
  }

  return Array.from(grouped.values())
    .map((entry) => ({
      assetCode: entry.assetCode,
      name: entry.name,
      marketValue: cents(entry.marketValue),
      quantity: entry.quantity,
      portfolioCount: entry.portfolios.size,
      weight: total > 0 ? entry.marketValue / total : 0,
    }))
    .sort((left, right) => right.marketValue - left.marketValue);
}
