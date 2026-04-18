"use client";

import { Search } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Input } from "@/components/ui/input";

export function TopBar({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <h1 className="text-base font-semibold tracking-tight">{title}</h1>
      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden sm:block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Buscar ativo, operação..."
            className="h-9 w-64 pl-8"
          />
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
