import { describe, it, expect } from "vitest";
import {
  cents,
  formatBRL,
  formatBRLSigned,
  formatPercent,
  formatQuantity,
} from "@/lib/money";

describe("money helpers", () => {
  it("formats integer cents as BRL", () => {
    expect(formatBRL(cents(100))).toMatch(/^R\$\s?1,00$/);
    expect(formatBRL(cents(123456))).toMatch(/^R\$\s?1\.234,56$/);
    expect(formatBRL(cents(0))).toMatch(/^R\$\s?0,00$/);
  });

  it("never uses float math (1/100 cent boundaries)", () => {
    // 0.10 + 0.20 in floats != 0.30, but we work in cents.
    const a = cents(10);
    const b = cents(20);
    expect(a + b).toBe(30);
    expect(formatBRL((a + b) as ReturnType<typeof cents>)).toMatch(/0,30/);
  });

  it("formats signed BRL with explicit sign", () => {
    expect(formatBRLSigned(cents(150))).toMatch(/^\+R\$\s?1,50$/);
    expect(formatBRLSigned(cents(-150))).toMatch(/^−R\$\s?1,50$/);
    expect(formatBRLSigned(cents(0))).toMatch(/^R\$\s?0,00$/);
  });

  it("formats percentages in pt-BR", () => {
    expect(formatPercent(0.1234)).toMatch(/12,34%/);
    expect(formatPercent(-0.05)).toMatch(/-5,00%/);
  });

  it("formats quantities in pt-BR", () => {
    expect(formatQuantity(1234)).toBe("1.234");
    expect(formatQuantity(0.5)).toBe("0,5");
  });
});
