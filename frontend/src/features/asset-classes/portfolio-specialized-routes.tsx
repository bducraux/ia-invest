"use client";

import OverviewPage from "@/app/(dashboard)/page";
import OperationsPage from "@/app/(dashboard)/operations/page";
import PositionsPage from "@/app/(dashboard)/positions/page";
import FixedIncomePage from "@/app/(dashboard)/fixed-income/page";
import { ClassFamilyOperationsPage, ClassFamilyOverviewPage, ClassFamilyPositionsPage } from "@/features/asset-classes/class-family-pages";
import { FixedIncomeOperationsPage } from "@/features/asset-classes/fixed-income-operations-page";
import { useDashboardScope } from "@/lib/dashboard-scope";
import { usePortfolios } from "@/lib/queries";

function useActivePortfolioSpecialization() {
  const scope = useDashboardScope();
  const portfoliosQuery = usePortfolios();
  const activePortfolio = (portfoliosQuery.data ?? []).find((portfolio) => portfolio.id === scope.portfolioId);

  return {
    isLoading: portfoliosQuery.isLoading,
    specialization: activePortfolio?.specialization ?? "GENERIC",
  };
}

function LoadingState() {
  return <OverviewPage />;
}

export function PortfolioSpecializedOverviewRoute() {
  const { isLoading, specialization } = useActivePortfolioSpecialization();
  if (isLoading) return <LoadingState />;

  switch (specialization) {
    case "RENDA_FIXA":
      return <FixedIncomePage />;
    case "RENDA_VARIAVEL":
      return <ClassFamilyOverviewPage classFamily="RENDA_VARIAVEL" />;
    case "CRIPTO":
      return <ClassFamilyOverviewPage classFamily="CRIPTO" />;
    case "PREVIDENCIA":
      return <ClassFamilyOverviewPage classFamily="PREVIDENCIA" />;
    case "INTERNACIONAL":
      return <ClassFamilyOverviewPage classFamily="INTERNACIONAL" />;
    default:
      return <OverviewPage />;
  }
}

export function PortfolioSpecializedPositionsRoute() {
  const { isLoading, specialization } = useActivePortfolioSpecialization();
  if (isLoading) return <PositionsPage />;

  switch (specialization) {
    case "RENDA_FIXA":
      return <FixedIncomePage />;
    case "RENDA_VARIAVEL":
      return <ClassFamilyPositionsPage classFamily="RENDA_VARIAVEL" />;
    case "CRIPTO":
      return <ClassFamilyPositionsPage classFamily="CRIPTO" />;
    case "PREVIDENCIA":
      return <ClassFamilyPositionsPage classFamily="PREVIDENCIA" />;
    case "INTERNACIONAL":
      return <ClassFamilyPositionsPage classFamily="INTERNACIONAL" />;
    default:
      return <PositionsPage />;
  }
}

export function PortfolioSpecializedOperationsRoute() {
  const { isLoading, specialization } = useActivePortfolioSpecialization();
  if (isLoading) return <OperationsPage />;

  switch (specialization) {
    case "RENDA_FIXA":
      return <FixedIncomeOperationsPage />;
    case "RENDA_VARIAVEL":
      return <ClassFamilyOperationsPage classFamily="RENDA_VARIAVEL" />;
    case "CRIPTO":
      return <ClassFamilyOperationsPage classFamily="CRIPTO" />;
    case "PREVIDENCIA":
      return <ClassFamilyOperationsPage classFamily="PREVIDENCIA" />;
    case "INTERNACIONAL":
      return <ClassFamilyOperationsPage classFamily="INTERNACIONAL" />;
    default:
      return <OperationsPage />;
  }
}
