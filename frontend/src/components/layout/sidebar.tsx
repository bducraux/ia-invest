"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  PieChart,
  ListOrdered,
  Coins,
  Upload,
  Settings,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/positions", label: "Posições", icon: PieChart },
  { href: "/operations", label: "Operações", icon: ListOrdered },
  { href: "/dividends", label: "Proventos", icon: Coins },
  { href: "/import", label: "Importar", icon: Upload },
  { href: "/settings", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
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
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
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
      </nav>
      <div className="border-t border-border p-4 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Carteira Principal</p>
        <p>BRL · sincronizado localmente</p>
      </div>
    </aside>
  );
}
