import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function KpiCard({
  title,
  value,
  subValue,
  trend,
  icon,
}: {
  title: string;
  value: string;
  subValue?: string;
  trend?: { label: string; positive: boolean };
  icon?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>{title}</CardTitle>
        {icon ? <div className="text-muted-foreground">{icon}</div> : null}
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-2xl font-semibold tabular tracking-tight">{value}</div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {subValue ? <span className="tabular">{subValue}</span> : null}
          {trend ? (
            <Badge variant={trend.positive ? "positive" : "negative"}>
              <span className={cn("tabular")}>{trend.label}</span>
            </Badge>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
