import { describe, expect, it } from "vitest";

import type { PositionWithPortfolio } from "@/lib/portfolio-aggregation";
import { cents } from "@/lib/money";
import {
  aggregateRendaVariavelExposure,
  buildRendaVariavelTypeSlices,
} from "@/features/asset-classes/renda-variavel-analytics";

const positions: PositionWithPortfolio[] = [
  {
    portfolioId: "rv-1",
    portfolioName: "Renda Variável 1",
    ownerId: "bob",
    ownerName: "Bob",
    assetCode: "BBAS3",
    name: "Banco do Brasil",
    assetClass: "ACAO",
    quantity: 10,
    avgPrice: cents(1000),
    marketPrice: cents(2000),
    marketValue: cents(20000),
    unrealizedPnl: cents(10000),
    unrealizedPnlPct: 1,
    weight: 0.4,
    quoteStatus: "avg_fallback",
    quoteSource: "avg_price",
  },
  {
    portfolioId: "rv-2",
    portfolioName: "Renda Variável 2",
    ownerId: "bob",
    ownerName: "Bob",
    assetCode: "BBAS3",
    name: "Banco do Brasil",
    assetClass: "ACAO",
    quantity: 5,
    avgPrice: cents(1200),
    marketPrice: cents(2200),
    marketValue: cents(11000),
    unrealizedPnl: cents(5000),
    unrealizedPnlPct: 0.8,
    weight: 0.2,
    quoteStatus: "avg_fallback",
    quoteSource: "avg_price",
  },
  {
    portfolioId: "rv-1",
    portfolioName: "Renda Variável 1",
    ownerId: "bob",
    ownerName: "Bob",
    assetCode: "HGLG11",
    name: "HGLG11",
    assetClass: "FII",
    quantity: 8,
    avgPrice: cents(15000),
    marketPrice: cents(17000),
    marketValue: cents(136000),
    unrealizedPnl: cents(16000),
    unrealizedPnlPct: 0.13,
    weight: 0.4,
    quoteStatus: "avg_fallback",
    quoteSource: "avg_price",
  },
];

describe("renda variavel analytics", () => {
  it("groups exposure by asset code across portfolios", () => {
    const exposures = aggregateRendaVariavelExposure(positions);

    expect(exposures[0].assetCode).toBe("HGLG11");
    expect(exposures[1].assetCode).toBe("BBAS3");
    expect(exposures[1].marketValue).toBe(31000);
    expect(exposures[1].quantity).toBe(15);
    expect(exposures[1].portfolioCount).toBe(2);
  });

  it("builds slices by renda variavel subtype", () => {
    const slices = buildRendaVariavelTypeSlices(positions);

    expect(slices.map((slice) => slice.label)).toEqual(["FIIs", "Ações"]);
    expect(slices.find((slice) => slice.assetClass === "ACAO")?.value).toBe(31000);
    expect(slices.find((slice) => slice.assetClass === "FII")?.value).toBe(136000);
  });
});
