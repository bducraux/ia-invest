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

// Normaliza espaços não-quebráveis (U+00A0) e estreitos (U+202F) usados pelo
// Intl em "R$ 1.234,56" / "1,23 %". As versões de ICU do Node e do navegador
// nem sempre concordam no caractere usado, o que provoca erros de hidratação
// no Next.js. Forçamos espaço comum em todas as saídas.
function normalizeSpaces(value: string): string {
  return value.replace(/[\u00A0\u202F]/g, " ");
}

export function formatBRL(value: Cents | number): string {
  return normalizeSpaces(brlCurrency.format(centsToBRL(value)));
}

export function formatBRLCompact(value: Cents | number): string {
  return normalizeSpaces(brlCurrencyCompact.format(centsToBRL(value)));
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
  return normalizeSpaces(percentPtBr.format(value));
}

export function formatQuantity(value: number): string {
  return normalizeSpaces(numberPtBr.format(value));
}
