import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WarningBadge } from "@/components/irpf/warning-badge";
import { formatNumberPtBr } from "@/lib/money";

describe("formatNumberPtBr", () => {
  it("renders cents as pt-BR plain number without currency symbol", () => {
    expect(formatNumberPtBr(15844)).toBe("158,44");
    expect(formatNumberPtBr(123456789)).toBe("1.234.567,89");
    expect(formatNumberPtBr(0)).toBe("0,00");
  });

  it("renders negative values keeping sign", () => {
    expect(formatNumberPtBr(-2500)).toBe("-25,00");
  });
});

describe("WarningBadge", () => {
  it("returns nothing when there are no warnings", () => {
    const { container } = render(<WarningBadge warnings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a single warning label", () => {
    render(<WarningBadge warnings={["cnpj_missing"]} />);
    expect(screen.getByText(/aten/i)).toBeInTheDocument();
  });

  it("renders a counter when multiple warnings are present", () => {
    render(<WarningBadge warnings={["cnpj_missing", "valor_zero"]} />);
    expect(screen.getByText(/2 alertas/i)).toBeInTheDocument();
  });

  it("includes payload from asset_metadata_missing in the tooltip", () => {
    const { container } = render(
      <WarningBadge warnings={["asset_metadata_missing:XPML11,KNRI11"]} />,
    );
    const badge = container.querySelector("[title]");
    expect(badge?.getAttribute("title") ?? "").toContain("XPML11,KNRI11");
  });
});
