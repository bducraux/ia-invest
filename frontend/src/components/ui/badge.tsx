import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Badge({
  className,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "muted" | "positive" | "negative" | "outline";
}) {
  const styles: Record<string, string> = {
    default: "bg-primary/15 text-primary",
    muted: "bg-muted text-muted-foreground",
    positive: "bg-positive/15 text-positive",
    negative: "bg-negative/15 text-negative",
    outline: "border border-border text-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}
