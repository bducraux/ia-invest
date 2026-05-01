import { describe, expect, it } from "vitest";

import { cents } from "@/lib/money";
import {
  deriveOwnerLabel,
  mergeOperations,
  mergePositions,
  toDividendEntries,
} from "@/lib/portfolio-aggregation";
import type { Operation, Portfolio, Position } from "@/types/domain";

const bobCripto: Portfolio = {
  id: "bob__cripto",
  name: "Cripto",
  currency: "BRL",
  allowedAssetTypes: ["crypto"],
  specialization: "CRIPTO",
  ownerId: "bob",
  owner: {
    id: "bob",
    name: "Bob",
    displayName: "Brunão",
    status: "active",
  },
};

const aliceRendaFixa: Portfolio = {
  id: "alice__renda-fixa",
  name: "Renda Fixa",
  currency: "BRL",
  allowedAssetTypes: ["cdb"],
  specialization: "RENDA_FIXA",
  ownerId: "alice",
  owner: { id: "alice", name: "Alice", status: "active" },
};

const samplePosition: Position = {
  assetCode: "BTC",
  name: "Bitcoin",
  assetClass: "CRIPTO",
  quantity: 1,
  avgPrice: cents(100_00),
  marketPrice: cents(150_00),
  marketValue: cents(150_00),
  unrealizedPnl: cents(50_00),
  unrealizedPnlPct: 0.5,
  weight: 1,
  quoteStatus: "live",
  quoteSource: "brapi",
};

const sampleOperation: Operation = {
  id: "1",
  date: "2026-04-20",
  assetCode: "BTC",
  type: "COMPRA",
  quantity: 1,
  unitPrice: cents(100_00),
  total: cents(100_00),
  source: "binance",
};

describe("deriveOwnerLabel", () => {
  it("prefers displayName over name", () => {
    expect(deriveOwnerLabel(bobCripto)).toEqual({
      ownerId: "bob",
      ownerName: "Brunão",
    });
  });

  it("falls back to name when displayName is missing", () => {
    expect(deriveOwnerLabel(aliceRendaFixa)).toEqual({
      ownerId: "alice",
      ownerName: "Alice",
    });
  });

  it("returns empty strings when portfolio is undefined", () => {
    expect(deriveOwnerLabel(undefined)).toEqual({ ownerId: "", ownerName: "" });
  });
});

describe("mergePositions / mergeOperations", () => {
  it("attaches owner fields to merged positions", () => {
    const merged = mergePositions(
      [bobCripto, aliceRendaFixa],
      [[samplePosition], [samplePosition]],
    );
    expect(merged).toHaveLength(2);
    expect(merged[0]).toMatchObject({
      portfolioId: "bob__cripto",
      portfolioName: "Cripto",
      ownerId: "bob",
      ownerName: "Brunão",
    });
    expect(merged[1]).toMatchObject({
      portfolioId: "alice__renda-fixa",
      ownerId: "alice",
      ownerName: "Alice",
    });
  });

  it("propagates owner through operations and dividend entries", () => {
    const dividendOp: Operation = { ...sampleOperation, type: "DIVIDENDO" };
    const merged = mergeOperations([bobCripto], [[dividendOp]]);
    const entries = toDividendEntries(merged);
    expect(entries[0]).toMatchObject({
      ownerId: "bob",
      ownerName: "Brunão",
      portfolioName: "Cripto",
    });
  });
});
