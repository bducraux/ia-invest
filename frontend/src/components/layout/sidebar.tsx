"use client";

import { useState } from "react";
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
  ChevronRight,
  ChartCandlestick,
  Bitcoin,
  ShieldCheck,
  Globe,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  buildScopedPath,
  CONTEXT_AWARE_SECTIONS,
  useDashboardScope,
} from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";
import { cn } from "@/lib/utils";

const patrimonioItems = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/positions", label: "Posições", icon: PieChart },
  { href: "/operations", label: "Operações", icon: ListOrdered },
  { href: "/dividends", label: "Proventos", icon: Coins },
  { href: "/fixed-income", label: "Renda fixa", icon: Landmark },
  { href: "/renda-variavel", label: "Renda variável", icon: ChartCandlestick },
  { href: "/cripto", label: "Criptomoedas", icon: Bitcoin },
  { href: "/previdencia", label: "Previdência", icon: ShieldCheck },
  { href: "/internacional", label: "Internacional", icon: Globe },
];

const systemItems = [
  { href: "/import", label: "Importar", icon: Upload },
  { href: "/settings", label: "Configurações", icon: Settings },
];

const portfolioSections = [
  { href: "/positions", label: "Posições" },
  { href: "/operations", label: "Operações" },
];

export function Sidebar() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const portfolios = portfoliosQuery.data ?? [];
  const [expandedPortfolios, setExpandedPortfolios] = useState<Record<string, boolean>>({});
  const activePortfolio = portfolios.find((portfolio) => portfolio.id === scope.portfolioId);

  function togglePortfolio(portfolioId: string) {
    setExpandedPortfolios((prev) => ({
      ...prev,
      [portfolioId]: !(prev[portfolioId] ?? false),
    }));
  }

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
        <div className="pb-3">
          <p className="px-3 pb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Patrimônio
          </p>

          {patrimonioItems.map((item) => {
            const isContextAware = CONTEXT_AWARE_SECTIONS.has(item.href);
            const href = isContextAware ? buildScopedPath(undefined, item.href) : item.href;
            const active =
              scope.isGlobalScope
              && (item.href === "/"
                ? scope.sectionPath === "/"
                : scope.sectionPath.startsWith(item.href));
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
        </div>

        <div className="border-t border-border/60 pt-3">
          <p className="px-3 pb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Carteiras
          </p>

          {portfolios.map((portfolio) => {
            const isActive = scope.portfolioId === portfolio.id;
            const overviewHref = buildScopedPath(portfolio.id, "/");
            const isExpanded = expandedPortfolios[portfolio.id] ?? isActive;

            return (
              <div key={portfolio.id} className="mb-2 rounded-lg border border-transparent px-1 py-1">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => togglePortfolio(portfolio.id)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
                    aria-label={isExpanded ? "Recolher carteira" : "Expandir carteira"}
                    aria-expanded={isExpanded}
                  >
                    <ChevronRight
                      className={cn("h-4 w-4 transition-transform", isExpanded ? "rotate-90" : "")}
                    />
                  </button>
                  <Link
                    href={overviewHref}
                    className={cn(
                      "flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md px-2 py-2 text-sm transition-colors",
                      isActive && scope.sectionPath === "/"
                        ? "bg-accent text-accent-foreground font-medium"
                        : isActive
                          ? "text-foreground"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <span className="truncate">{portfolio.name}</span>
                    {isActive ? <Badge variant="outline">Ativa</Badge> : null}
                  </Link>
                </div>

                {isExpanded ? (
                  <div className="mt-1 space-y-1 pl-9">
                    {portfolioSections.map((section) => {
                      const href = buildScopedPath(portfolio.id, section.href);
                      const isSectionActive = isActive && scope.sectionPath === section.href;

                      return (
                        <Link
                          key={`${portfolio.id}-${section.href}`}
                          href={href}
                          className={cn(
                            "block rounded-md px-2 py-1.5 text-sm transition-colors",
                            isSectionActive
                              ? "bg-accent text-accent-foreground font-medium"
                              : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                          )}
                        >
                          {section.label}
                        </Link>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        <div className="border-t border-border/60 pt-3">
          <p className="px-3 pb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Sistema
          </p>

          {systemItems.map((item) => {
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
        </div>
      </nav>
      <div className="border-t border-border p-4 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Contexto ativo</p>
        <p>
          {scope.isGlobalScope
            ? "Patrimônio consolidado"
            : activePortfolio?.name ?? "Carteira selecionada"}
        </p>
      </div>
    </aside>
  );
}
