import type { Portfolio } from "@/types/domain";

export interface OwnerGroup {
  ownerId: string;
  ownerName: string;
  portfolios: Portfolio[];
}

/**
 * Group portfolios by their owner. Portfolios with no `owner` block are
 * grouped under the synthetic owner derived from `ownerId`.
 *
 * Owners are sorted alphabetically by display name; portfolios within each
 * owner keep the input order (which already reflects the API's canonical
 * sort by name).
 */
export function groupPortfoliosByOwner(portfolios: Portfolio[]): OwnerGroup[] {
  const map = new Map<string, OwnerGroup>();
  for (const portfolio of portfolios) {
    const ownerId = portfolio.ownerId || portfolio.owner?.id || "default";
    const ownerName =
      portfolio.owner?.displayName || portfolio.owner?.name || ownerId;
    let group = map.get(ownerId);
    if (!group) {
      group = { ownerId, ownerName, portfolios: [] };
      map.set(ownerId, group);
    }
    group.portfolios.push(portfolio);
  }

  return Array.from(map.values()).sort((a, b) =>
    a.ownerName.localeCompare(b.ownerName, "pt-BR"),
  );
}

/**
 * Build the composite key used to track expansion state for the
 * owner-grouped sidebar accordion (`${ownerId}:${portfolioId}`).
 */
export function portfolioExpansionKey(
  ownerId: string,
  portfolioId: string,
): string {
  return `${ownerId}:${portfolioId}`;
}
