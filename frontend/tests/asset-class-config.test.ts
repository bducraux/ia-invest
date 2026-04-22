import { describe, expect, it } from "vitest";

import { GLOBAL_CLASS_ITEMS, specializationLabel } from "@/lib/asset-class-config";

describe("asset class config", () => {
  it("exposes the supported global class pages", () => {
    expect(GLOBAL_CLASS_ITEMS.map((item) => item.href)).toEqual([
      "/fixed-income",
      "/renda-variavel",
      "/cripto",
      "/previdencia",
    ]);
  });

  it("renders user-facing labels for supported specializations", () => {
    expect(specializationLabel("RENDA_FIXA")).toBe("Renda fixa");
    expect(specializationLabel("RENDA_VARIAVEL")).toBe("Renda variável");
    expect(specializationLabel("CRIPTO")).toBe("Criptomoedas");
    expect(specializationLabel("PREVIDENCIA")).toBe("Previdência");
  });
});
