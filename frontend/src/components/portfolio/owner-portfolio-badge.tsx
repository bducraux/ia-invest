import { Badge } from "@/components/ui/badge";

interface OwnerPortfolioBadgeProps {
  portfolioName: string;
  ownerName?: string | null;
}

/**
 * Compact badge that always renders the portfolio name, prefixed with the
 * owner display name when available. Used in consolidated/global listings to
 * make the multi-tenancy explicit ("Bruno · Cripto").
 */
export function OwnerPortfolioBadge({
  portfolioName,
  ownerName,
}: OwnerPortfolioBadgeProps) {
  const label = ownerName && ownerName.trim().length > 0
    ? `${ownerName} · ${portfolioName}`
    : portfolioName;
  return <Badge variant="outline">{label}</Badge>;
}
