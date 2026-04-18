export type Cents = number & { readonly __brand: "cents" };

function toCents(value: number): Cents {
  return Math.trunc(value) as Cents;
}

export function cents(value: number): Cents {
  return toCents(value);
}

const brlCurrency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const brlCurrencyCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  compactDisplay: "short",
  maximumFractionDigits: 1,
});

const numberPtBr = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 8,
});

const percentPtBr = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function centsToBRL(value: Cents | number): number {
  return Number(value) / 100;
}

export function formatBRL(value: Cents | number): string {
  return brlCurrency.format(centsToBRL(value));
}

export function formatBRLCompact(value: Cents | number): string {
  return brlCurrencyCompact.format(centsToBRL(value));
}

export function formatBRLSigned(value: Cents | number): string {
  const asNumber = Number(value);
  if (asNumber === 0) {
    return formatBRL(0);
  }

  const sign = asNumber > 0 ? "+" : "−";
  return `${sign}${formatBRL(Math.abs(asNumber))}`;
}

export function formatPercent(value: number): string {
  return percentPtBr.format(value);
}

export function formatQuantity(value: number): string {
  return numberPtBr.format(value);
}
