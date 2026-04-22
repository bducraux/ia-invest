"use client";

import { usePathname } from "next/navigation";

export const CONTEXT_AWARE_SECTIONS = new Set([
  "/",
  "/positions",
  "/operations",
  "/dividends",
  "/fixed-income",
]);

function normalizeSectionPath(path: string): string {
  if (!path || path === "/") {
    return "/";
  }
  return path.startsWith("/") ? path : `/${path}`;
}

export function buildScopedPath(portfolioId: string | undefined, sectionPath: string): string {
  const normalized = normalizeSectionPath(sectionPath);
  if (!portfolioId) {
    return normalized;
  }
  if (normalized === "/") {
    return `/portfolio/${portfolioId}`;
  }
  return `/portfolio/${portfolioId}${normalized}`;
}

export function useDashboardScope() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const isPortfolioScope = segments[0] === "portfolio" && Boolean(segments[1]);
  const portfolioId = isPortfolioScope ? segments[1] : undefined;
  const sectionSegments = isPortfolioScope ? segments.slice(2) : segments;
  const sectionPath = normalizeSectionPath(sectionSegments.join("/"));

  return {
    pathname,
    isPortfolioScope,
    isGlobalScope: !isPortfolioScope,
    portfolioId,
    sectionPath,
  };
}