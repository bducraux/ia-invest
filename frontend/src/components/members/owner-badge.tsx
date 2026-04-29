import { User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Owner } from "@/types/domain";
import { cn } from "@/lib/utils";

interface OwnerBadgeProps {
  owner: Owner | null | undefined;
  className?: string;
}

/**
 * Small visual chip identifying a portfolio owner (member).
 *
 * Falls back to a placeholder badge when the owner data is missing.
 */
export function OwnerBadge({ owner, className }: OwnerBadgeProps) {
  const label = owner?.displayName || owner?.name || owner?.id || "—";
  return (
    <Badge
      variant="outline"
      className={cn("gap-1 text-[10px] uppercase tracking-wider", className)}
    >
      <User className="h-3 w-3" aria-hidden />
      <span className="truncate">{label}</span>
    </Badge>
  );
}
