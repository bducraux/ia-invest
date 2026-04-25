import type { PortfolioSpecialization } from "@/types/domain";

export type SupportedPortfolioClass = Exclude<PortfolioSpecialization, "GENERIC">;

export type ClassFamily = "RENDA_VARIAVEL" | "CRIPTO" | "PREVIDENCIA" | "INTERNACIONAL";

export const GLOBAL_CLASS_ITEMS: Array<{
  href: string;
  label: string;
  specialization: SupportedPortfolioClass;
}> = [
  { href: "/fixed-income", label: "Renda fixa", specialization: "RENDA_FIXA" },
  { href: "/renda-variavel", label: "Renda variável", specialization: "RENDA_VARIAVEL" },
  { href: "/cripto", label: "Criptomoedas", specialization: "CRIPTO" },
  { href: "/previdencia", label: "Previdência", specialization: "PREVIDENCIA" },
  { href: "/internacional", label: "Internacional", specialization: "INTERNACIONAL" },
];

export function isSupportedPortfolioClass(
  specialization: PortfolioSpecialization | undefined,
): specialization is SupportedPortfolioClass {
  return Boolean(
    specialization
      && ["RENDA_FIXA", "RENDA_VARIAVEL", "CRIPTO", "PREVIDENCIA", "INTERNACIONAL"].includes(specialization),
  );
}

export function specializationLabel(specialization: SupportedPortfolioClass): string {
  switch (specialization) {
    case "RENDA_FIXA":
      return "Renda fixa";
    case "RENDA_VARIAVEL":
      return "Renda variável";
    case "CRIPTO":
      return "Criptomoedas";
    case "PREVIDENCIA":
      return "Previdência";
    case "INTERNACIONAL":
      return "Internacional";
  }
}
