import { describe, expect, it } from "vitest";
import {
  groupPortfoliosByOwner,
  portfolioExpansionKey,
} from "@/lib/portfolio-grouping";
import type { Portfolio } from "@/types/domain";

function portfolio(
  id: string,
  ownerId: string,
  ownerName?: string,
): Portfolio {
  return {
    id,
    name: id.toUpperCase(),
    currency: "BRL",
    allowedAssetTypes: ["stock"],
    specialization: "RENDA_VARIAVEL",
    ownerId,
    owner: { id: ownerId, name: ownerName ?? ownerId, status: "active" },
  };
}

describe("portfolio-grouping", () => {
  it("groups portfolios by owner with the owner display name", () => {
    const groups = groupPortfoliosByOwner([
      portfolio("rv-bob", "bob", "Bob"),
      portfolio("rf-alice", "alice", "Alice"),
      portfolio("crypto-bob", "bob", "Bob"),
    ]);

    expect(groups).toHaveLength(2);
    const bob = groups.find((g) => g.ownerId === "bob");
    expect(bob?.portfolios.map((p) => p.id)).toEqual([
      "rv-bob",
      "crypto-bob",
    ]);
    const alice = groups.find((g) => g.ownerId === "alice");
    expect(alice?.portfolios.map((p) => p.id)).toEqual(["rf-alice"]);
  });

  it("sorts owner groups alphabetically by display name", () => {
    const groups = groupPortfoliosByOwner([
      portfolio("a", "z", "Zé"),
      portfolio("b", "a", "Ana"),
      portfolio("c", "m", "Marina"),
    ]);
    expect(groups.map((g) => g.ownerName)).toEqual(["Ana", "Marina", "Zé"]);
  });

  it("falls back to ownerId when owner block is missing", () => {
    const p: Portfolio = {
      id: "x",
      name: "X",
      currency: "BRL",
      allowedAssetTypes: ["stock"],
      specialization: "RENDA_VARIAVEL",
      ownerId: "ghost",
    };
    const groups = groupPortfoliosByOwner([p]);
    expect(groups[0].ownerId).toBe("ghost");
    expect(groups[0].ownerName).toBe("ghost");
  });

  it("uses 'default' when no ownerId is set", () => {
    const groups = groupPortfoliosByOwner([
      // @ts-expect-error simulating a malformed payload
      { id: "x", name: "X", currency: "BRL", allowedAssetTypes: [], specialization: "GENERIC" },
    ]);
    expect(groups[0].ownerId).toBe("default");
  });

  it("composes a stable expansion key", () => {
    expect(portfolioExpansionKey("bob", "rv")).toBe("bob:rv");
  });
});
