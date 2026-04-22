"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface SortableHeadProps {
  col: string;
  sortKey: string;
  direction: "asc" | "desc";
  onSort: (col: string) => void;
  className?: string;
  children: React.ReactNode;
}

export function SortableHead({
  col,
  sortKey,
  direction,
  onSort,
  className,
  children,
}: SortableHeadProps) {
  const isActive = col === sortKey;
  const isRight = className?.includes("text-right");

  return (
    <TableHead
      className={cn("cursor-pointer select-none hover:text-foreground", className)}
      onClick={() => onSort(col)}
    >
      <span
        className={cn(
          "inline-flex items-center gap-1",
          isRight && "w-full justify-end",
        )}
      >
        {children}
        {isActive ? (
          direction === "asc" ? (
            <ArrowUp className="h-3 w-3 shrink-0" />
          ) : (
            <ArrowDown className="h-3 w-3 shrink-0" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 shrink-0 opacity-40" />
        )}
      </span>
    </TableHead>
  );
}
