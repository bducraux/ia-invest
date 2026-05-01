import { describe, expect, it } from "vitest";

import {
  CONTEXT_AWARE_SECTIONS,
  buildScopedPath,
} from "@/lib/dashboard-scope";

describe("dashboard scope helpers", () => {
  it("includes fixed-income as context-aware section", () => {
    expect(CONTEXT_AWARE_SECTIONS.has("/fixed-income")).toBe(true);
  });

  it("builds fixed-income scoped path for selected portfolio", () => {
    expect(buildScopedPath("renda-fixa-bob", "/fixed-income")).toBe(
      "/portfolio/renda-fixa-bob/fixed-income",
    );
  });
});
