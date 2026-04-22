"use client";

import { Search, RefreshCw } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Input } from "@/components/ui/input";
import { refreshQuotes } from "@/lib/api";
import { useToastContext } from "@/lib/toast-context";

export function TopBar({ title }: { title: string }) {
  const scope = useDashboardScope();
  const queryClient = useQueryClient();
  const portfoliosQuery = usePortfolios();
  const toast = useToastContext();
  const activePortfolio = (portfoliosQuery.data ?? []).find(
    (portfolio) => portfolio.id === scope.portfolioId,
  );

  const scopeLabel = scope.isGlobalScope
    ? "Patrimônio"
    : activePortfolio?.name ?? "Carteira";

  const refreshMutation = useMutation({
    mutationFn: () => refreshQuotes(scope.portfolioId),
    onSuccess: async (data) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolios"] }),
      ]);
      const successMessage = `Preços atualizados: ${data.liveCount} ao vivo, ${data.cacheStaleCount} em cache, ${data.avgFallbackCount} preço médio`;
      toast.success(successMessage);
    },
    onError: (error: Error) => {
      toast.error(`Erro ao atualizar preços: ${error.message}`);
    },
  });

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-2">
        <h1 className="text-base font-semibold tracking-tight">{title}</h1>
        <Badge variant="outline">{scopeLabel}</Badge>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-transparent px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
          Atualizar preços
        </button>
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
