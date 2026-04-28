const datePtBr = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

const monthPtBr = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "2-digit",
  timeZone: "UTC",
});

// Espaços NBSP (U+00A0) e NNBSP (U+202F) usados pelo Intl variam entre as
// versões de ICU do Node e do navegador, causando erros de hidratação no Next.
function normalizeSpaces(value: string): string {
  return value.replace(/[\u00A0\u202F]/g, " ");
}

export function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return isoDate;
  }
  return normalizeSpaces(datePtBr.format(date));
}

export function formatMonth(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return isoDate;
  }
  return normalizeSpaces(monthPtBr.format(date));
}
