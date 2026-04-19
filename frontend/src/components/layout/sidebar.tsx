"use client";

import Link from "next/link";
import {
  LayoutDashboard,
  PieChart,
  ListOrdered,
  Coins,
  Landmark,
  Upload,
  Settings,
  TrendingUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  buildScopedPath,
  CONTEXT_AWARE_SECTIONS,
  useDashboardScope,
} from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";
import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/positions", label: "Posições", icon: PieChart },
  { href: "/operations", label: "Operações", icon: ListOrdered },
  { href: "/dividends", label: "Proventos", icon: Coins },
  { href: "/fixed-income", label: "Renda fixa", icon: Landmark },
  { href: "/import", label: "Importar", icon: Upload },
  { href: "/settings", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);
  const sectionForSwitch = CONTEXT_AWARE_SECTIONS.has(scope.sectionPath)
    ? scope.sectionPath
    : "/";

  return (
    <aside className="hidden w-60 shrink-0 border-r border-border bg-card/40 md:flex md:flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <TrendingUp className="h-4 w-4" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">IA-Invest</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            local-first
          </span>
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {items.map((item) => {
          const isContextAware = CONTEXT_AWARE_SECTIONS.has(item.href);
          const href = isContextAware ? buildScopedPath(scope.portfolioId, item.href) : item.href;
          const active =
            item.href === "/"
              ? scope.sectionPath === "/"
              : scope.sectionPath.startsWith(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}

        <div className="pt-3">
          <p className="px-3 pb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Portfolios
          </p>

          <Link
            href={buildScopedPath(undefined, sectionForSwitch)}
            className={cn(
              "mb-1 flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors",
              scope.isGlobalScope
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
            )}
          >
            <span>Família (consolidado)</span>
            <Badge variant="outline">Global</Badge>
          </Link>

          {portfolios.map((portfolio) => {
            const isActive = scope.portfolioId === portfolio.id;
            const href = buildScopedPath(portfolio.id, sectionForSwitch);

            return (
              <Link
                key={portfolio.id}
                href={href}
                className={cn(
                  "mb-1 flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                <span className="truncate">{portfolio.name}</span>
                {isActive ? <Badge variant="outline">Ativo</Badge> : null}
              </Link>
            );
          })}
        </div>
      </nav>
      <div className="border-t border-border p-4 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Contexto ativo</p>
        <p>
          {scope.isGlobalScope
            ? "Todas as carteiras"
            : activePortfolio?.name ?? "Portfolio selecionado"}
        </p>
      </div>
    </aside>
  );
}
