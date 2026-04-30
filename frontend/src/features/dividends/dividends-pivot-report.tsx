"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatBRL, formatPercent } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { OperationWithPortfolio } from "@/lib/portfolio-aggregation";

// ---------------------------------------------------------------------------
// Types & helpers
// ---------------------------------------------------------------------------

const PROVENT_TYPES = new Set(["DIVIDENDO", "JCP", "RENDIMENTO"]);

const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

type AssetClass = "FII" | "ACAO" | "FI_AGRO" | "BDR" | "ETF";

const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  FII: "FII",
  ACAO: "Ação",
  FI_AGRO: "FI-Agro",
  BDR: "BDR",
  ETF: "ETF",
};

// Tickers conhecidos de FI-Agro listados na B3 (heurística — extender se necessário).
const FI_AGRO_TICKERS = new Set([
  "BTAL11", "BTRA11", "AGRX11", "AGCX11", "RZAG11", "BIRA11", "OIAG11", "BLAG11", "VGAG11",
]);

function classifyAsset(assetCode: string, assetType?: string): AssetClass {
  const code = assetCode.toUpperCase();
  if (FI_AGRO_TICKERS.has(code)) return "FI_AGRO";
  // BDRs: 4 letras + 32/33/34/35
  if (/^[A-Z]{4}3[2345]$/.test(code)) return "BDR";
  // ETF padrão B3: BOVA11, IVVB11, etc. Alguns ETFs / FIIs colidem. Prioriza FII via asset_type.
  const t = (assetType || "").toLowerCase();
  if (t === "fii") return "FII";
  if (t === "etf") return "ETF";
  if (t === "stock") return "ACAO";
  if (/11$/.test(code)) return "FII";
  return "ACAO";
}

type PeriodMode = "max" | "ytd" | "12m" | "custom";

interface Period {
  mode: PeriodMode;
  // For custom mode (inclusive months as YYYY-MM)
  start?: string;
  end?: string;
}

type Metric = "value" | "yield";

interface Filters {
  memberIds: Set<string> | null; // null = all
  assetClasses: Set<AssetClass> | null; // null = all available
  ticker: string;
  period: Period;
  metric: Metric;
}

interface YearRow {
  year: number;
  months: (number | null)[]; // 12 entries (cents or null)
  total: number;
  count: number;
  byAsset: Map<string, AssetYearRow>;
}

interface AssetYearRow {
  assetCode: string;
  months: (number | null)[];
  total: number;
}

// ---------------------------------------------------------------------------
// Outside-click hook
// ---------------------------------------------------------------------------

function useOutsideClick<T extends HTMLElement>(
  onClose: () => void,
  enabled: boolean,
) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!enabled) return;
    function handler(ev: MouseEvent) {
      if (!ref.current) return;
      if (ref.current.contains(ev.target as Node)) return;
      onClose();
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose, enabled]);
  return ref;
}

// ---------------------------------------------------------------------------
// Popover wrapper
// ---------------------------------------------------------------------------

function Popover({
  trigger,
  isOpen,
  onClose,
  children,
  align = "left",
}: {
  trigger: React.ReactNode;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  const ref = useOutsideClick<HTMLDivElement>(onClose, isOpen);
  return (
    <div className="relative" ref={ref}>
      {trigger}
      {isOpen ? (
        <div
          className={cn(
            "absolute top-[calc(100%+4px)] z-30 min-w-[220px] rounded-md border border-border bg-card p-2 shadow-lg",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Month picker (for "Definir" period)
// ---------------------------------------------------------------------------

function MonthPicker({
  value,
  minYear,
  maxYear,
  onPick,
}: {
  value: string | undefined;
  minYear: number;
  maxYear: number;
  onPick: (ym: string) => void;
}) {
  const [year, setYear] = useState(() => {
    if (value) return parseInt(value.slice(0, 4), 10);
    return maxYear;
  });
  const selectedMonth = value && parseInt(value.slice(0, 4), 10) === year
    ? parseInt(value.slice(5, 7), 10) - 1
    : -1;

  return (
    <div className="w-[220px]">
      <div className="flex items-center justify-between px-1 pb-2">
        <button
          type="button"
          className="rounded px-2 py-1 text-sm hover:bg-accent disabled:opacity-30"
          disabled={year <= minYear}
          onClick={() => setYear((y) => Math.max(minYear, y - 1))}
          aria-label="Ano anterior"
        >
          ◀
        </button>
        <span className="text-sm font-semibold">{year}</span>
        <button
          type="button"
          className="rounded px-2 py-1 text-sm hover:bg-accent disabled:opacity-30"
          disabled={year >= maxYear}
          onClick={() => setYear((y) => Math.min(maxYear, y + 1))}
          aria-label="Próximo ano"
        >
          ▶
        </button>
      </div>
      <div className="grid grid-cols-3 gap-1">
        {MONTHS.map((m, i) => (
          <button
            key={m}
            type="button"
            className={cn(
              "rounded px-2 py-1 text-xs hover:bg-accent",
              selectedMonth === i ? "bg-primary text-primary-foreground hover:bg-primary/90" : "",
            )}
            onClick={() => onPick(`${year}-${String(i + 1).padStart(2, "0")}`)}
          >
            {m}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function periodLabel(period: Period, dataYears: number[]): string {
  const currentYear = new Date().getFullYear();
  switch (period.mode) {
    case "ytd":
      return String(currentYear);
    case "12m":
      return "12 meses";
    case "custom": {
      const fmt = (v?: string) =>
        v ? `${MONTHS[parseInt(v.slice(5, 7), 10) - 1]}/${v.slice(0, 4)}` : "—";
      return `${fmt(period.start)} → ${fmt(period.end)}`;
    }
    case "max":
    default:
      if (dataYears.length === 0) return "Máximo";
      return `Máximo (${Math.min(...dataYears)}–${Math.max(...dataYears)})`;
  }
}

function periodBounds(period: Period): { startMonth?: string; endMonth?: string } {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  switch (period.mode) {
    case "ytd":
      return { startMonth: `${yyyy}-01`, endMonth: `${yyyy}-${mm}` };
    case "12m": {
      const past = new Date(today.getFullYear(), today.getMonth() - 11, 1);
      return {
        startMonth: `${past.getFullYear()}-${String(past.getMonth() + 1).padStart(2, "0")}`,
        endMonth: `${yyyy}-${mm}`,
      };
    }
    case "custom":
      return { startMonth: period.start, endMonth: period.end };
    case "max":
    default:
      return {};
  }
}

function inRange(monthKey: string, bounds: { startMonth?: string; endMonth?: string }): boolean {
  if (bounds.startMonth && monthKey < bounds.startMonth) return false;
  if (bounds.endMonth && monthKey > bounds.endMonth) return false;
  return true;
}

// Tailwind heatmap classes — 5 buckets.
function heatmapClass(value: number, max: number): string {
  if (value <= 0 || max <= 0) return "";
  const ratio = value / max;
  if (ratio < 0.2) return "bg-sky-50 dark:bg-sky-950/30";
  if (ratio < 0.4) return "bg-sky-100 dark:bg-sky-900/40";
  if (ratio < 0.6) return "bg-sky-200 dark:bg-sky-800/50";
  if (ratio < 0.8) return "bg-sky-300 dark:bg-sky-700/60";
  return "bg-sky-400 dark:bg-sky-600/70 text-sky-950 dark:text-sky-50";
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface DividendsPivotReportProps {
  operations: OperationWithPortfolio[];
  /** Current portfolio market value in cents — denominator for the Yield mode. */
  portfolioValueCents: number | null;
}

export function DividendsPivotReport({
  operations,
  portfolioValueCents,
}: DividendsPivotReportProps) {
  // Derive provento operations once.
  const proventoOps = useMemo(
    () =>
      operations
        .filter((op) => PROVENT_TYPES.has(op.type))
        .map((op) => ({
          ...op,
          monthKey: op.date.slice(0, 7), // YYYY-MM
          year: parseInt(op.date.slice(0, 4), 10),
          monthIdx: parseInt(op.date.slice(5, 7), 10) - 1,
          assetClass: classifyAsset(op.assetCode, op.assetType),
        })),
    [operations],
  );

  const dataYears = useMemo(() => {
    const set = new Set<number>();
    for (const op of proventoOps) set.add(op.year);
    return Array.from(set).sort();
  }, [proventoOps]);

  const tickerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const op of proventoOps) set.add(op.assetCode);
    return Array.from(set).sort();
  }, [proventoOps]);

  // Members derived from operations (ownerId/ownerName).
  const memberOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const op of proventoOps) {
      const id = op.ownerId || "default";
      if (!map.has(id)) map.set(id, op.ownerName || id);
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  }, [proventoOps]);

  // Asset classes actually present in the data.
  const availableClasses = useMemo(() => {
    const set = new Set<AssetClass>();
    for (const op of proventoOps) set.add(op.assetClass);
    const order: AssetClass[] = ["ACAO", "FII", "FI_AGRO", "ETF", "BDR"];
    return order.filter((c) => set.has(c));
  }, [proventoOps]);

  // Filters state.
  const [filterBarOpen, setFilterBarOpen] = useState(true);
  const [filters, setFilters] = useState<Filters>({
    memberIds: null,
    assetClasses: null,
    ticker: "",
    period: { mode: "max" },
    metric: "value",
  });

  // Open popover state — only one at a time.
  const [openPopover, setOpenPopover] = useState<
    "members" | "classes" | "ticker" | "period" | "metric" | null
  >(null);

  // Filter operations.
  const filteredOps = useMemo(() => {
    const bounds = periodBounds(filters.period);
    const t = filters.ticker.trim().toUpperCase();
    return proventoOps.filter((op) => {
      if (filters.memberIds && !filters.memberIds.has(op.ownerId || "default")) return false;
      if (filters.assetClasses && !filters.assetClasses.has(op.assetClass)) return false;
      if (t && op.assetCode !== t) return false;
      if (!inRange(op.monthKey, bounds)) return false;
      return true;
    });
  }, [proventoOps, filters]);

  // Pivot.
  const yearRows = useMemo<YearRow[]>(() => {
    const byYear = new Map<number, YearRow>();
    for (const op of filteredOps) {
      let row = byYear.get(op.year);
      if (!row) {
        row = {
          year: op.year,
          months: Array(12).fill(null),
          total: 0,
          count: 0,
          byAsset: new Map(),
        };
        byYear.set(op.year, row);
      }
      const cur = row.months[op.monthIdx] ?? 0;
      row.months[op.monthIdx] = cur + op.total;
      row.total += op.total;
      row.count += 1;

      let asset = row.byAsset.get(op.assetCode);
      if (!asset) {
        asset = {
          assetCode: op.assetCode,
          months: Array(12).fill(null),
          total: 0,
        };
        row.byAsset.set(op.assetCode, asset);
      }
      asset.months[op.monthIdx] = (asset.months[op.monthIdx] ?? 0) + op.total;
      asset.total += op.total;
    }
    return Array.from(byYear.values()).sort((a, b) => a.year - b.year);
  }, [filteredOps]);

  const maxMonthValue = useMemo(() => {
    let max = 0;
    for (const row of yearRows) {
      for (const v of row.months) if (v && v > max) max = v;
    }
    return max;
  }, [yearRows]);

  const grandTotal = yearRows.reduce((acc, r) => acc + r.total, 0);

  // Drill-down rows expanded.
  const [expandedYears, setExpandedYears] = useState<Set<number>>(new Set());

  // Convert cents → display value depending on metric.
  function displayCellMain(cents: number | null): string {
    if (cents == null || cents === 0) return "";
    if (filters.metric === "value") return formatBRL(cents);
    if (!portfolioValueCents || portfolioValueCents <= 0) return "—";
    return formatPercent(cents / portfolioValueCents);
  }

  function displayTotal(cents: number): string {
    if (cents <= 0) return "—";
    if (filters.metric === "value") return formatBRL(cents);
    if (!portfolioValueCents || portfolioValueCents <= 0) return "—";
    return formatPercent(cents / portfolioValueCents);
  }

  function displayAverage(cents: number, monthsFilled: number): string {
    if (monthsFilled === 0) return "—";
    const avgCents = Math.round(cents / monthsFilled);
    if (filters.metric === "value") return formatBRL(avgCents);
    if (!portfolioValueCents || portfolioValueCents <= 0) return "—";
    return formatPercent(avgCents / portfolioValueCents);
  }

  function variation(curr: number, prev: number): { pct: number | null; arrow: "up" | "down" | null } {
    if (prev <= 0) return { pct: null, arrow: null };
    const diff = (curr - prev) / prev;
    return { pct: diff, arrow: diff >= 0 ? "up" : "down" };
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base text-foreground">Relatório mensal de proventos</CardTitle>
            <CardDescription>
              Total no período: <strong className="text-foreground">{formatBRL(grandTotal)}</strong>
              {filters.metric === "yield" && portfolioValueCents ? (
                <>
                  {" "}
                  · DY estimado vs valor atual da carteira ({formatBRL(portfolioValueCents)})
                </>
              ) : null}
            </CardDescription>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2">
          {!filterBarOpen ? (
            <Button variant="outline" size="sm" onClick={() => setFilterBarOpen(true)}>
              <span aria-hidden>⚙</span> Filtrar
            </Button>
          ) : (
            <>
              {/* Group 1: Membros / Classe / Ativo */}
              <div className="flex items-center rounded-md border border-border bg-card">
                <Popover
                  isOpen={openPopover === "members"}
                  onClose={() => setOpenPopover(null)}
                  trigger={
                    <button
                      type="button"
                      onClick={() =>
                        setOpenPopover(openPopover === "members" ? null : "members")
                      }
                      className="flex h-8 items-center gap-1 rounded-l-md px-3 text-xs font-medium hover:bg-accent"
                    >
                      <span aria-hidden>👤</span>
                      {filters.memberIds == null
                        ? "Todos"
                        : filters.memberIds.size === 1
                          ? memberOptions.find((m) => filters.memberIds!.has(m.id))?.name ?? "Membro"
                          : `${filters.memberIds.size} membros`}
                      <span aria-hidden>▾</span>
                    </button>
                  }
                >
                  <CheckboxList
                    options={memberOptions.map((m) => ({ value: m.id, label: m.name }))}
                    selected={filters.memberIds ?? new Set(memberOptions.map((m) => m.id))}
                    onChange={(set) =>
                      setFilters((f) => ({
                        ...f,
                        memberIds: set.size === memberOptions.length ? null : set,
                      }))
                    }
                  />
                </Popover>

                <span className="h-6 w-px bg-border" />

                <Popover
                  isOpen={openPopover === "classes"}
                  onClose={() => setOpenPopover(null)}
                  trigger={
                    <button
                      type="button"
                      onClick={() =>
                        setOpenPopover(openPopover === "classes" ? null : "classes")
                      }
                      className="flex h-8 items-center gap-1 px-3 text-xs font-medium hover:bg-accent"
                    >
                      <span aria-hidden>🗂</span>
                      {filters.assetClasses == null
                        ? "Todas as classes"
                        : filters.assetClasses.size === 1
                          ? ASSET_CLASS_LABEL[
                              Array.from(filters.assetClasses)[0] as AssetClass
                            ]
                          : `${filters.assetClasses.size} classes`}
                      <span aria-hidden>▾</span>
                    </button>
                  }
                >
                  <CheckboxList
                    options={availableClasses.map((c) => ({
                      value: c,
                      label: ASSET_CLASS_LABEL[c],
                    }))}
                    selected={
                      (filters.assetClasses ?? new Set<AssetClass>(availableClasses)) as Set<string>
                    }
                    onChange={(set) =>
                      setFilters((f) => ({
                        ...f,
                        assetClasses:
                          set.size === availableClasses.length
                            ? null
                            : (set as Set<AssetClass>),
                      }))
                    }
                  />
                </Popover>

                <span className="h-6 w-px bg-border" />

                <Popover
                  isOpen={openPopover === "ticker"}
                  onClose={() => setOpenPopover(null)}
                  trigger={
                    <button
                      type="button"
                      onClick={() =>
                        setOpenPopover(openPopover === "ticker" ? null : "ticker")
                      }
                      className="flex h-8 items-center gap-1 rounded-r-md px-3 text-xs font-medium hover:bg-accent"
                    >
                      <span aria-hidden>🏷</span>
                      {filters.ticker || "Ativo"}
                      {filters.ticker ? (
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation();
                            setFilters((f) => ({ ...f, ticker: "" }));
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              setFilters((f) => ({ ...f, ticker: "" }));
                            }
                          }}
                          className="ml-1 rounded px-1 text-muted-foreground hover:bg-accent"
                          aria-label="Limpar ativo"
                        >
                          ×
                        </span>
                      ) : (
                        <span aria-hidden>▾</span>
                      )}
                    </button>
                  }
                >
                  <TickerPicker
                    options={tickerOptions}
                    selected={filters.ticker}
                    onPick={(t) => {
                      setFilters((f) => ({ ...f, ticker: t }));
                      setOpenPopover(null);
                    }}
                  />
                </Popover>
              </div>

              {/* Group 2: Período */}
              <div className="flex items-center rounded-md border border-border bg-card">
                {filters.period.mode === "custom" ? (
                  <CustomPeriodControls
                    period={filters.period}
                    onChange={(p) => setFilters((f) => ({ ...f, period: p }))}
                    minYear={dataYears[0] ?? new Date().getFullYear()}
                    maxYear={new Date().getFullYear()}
                  />
                ) : (
                  <>
                    <Popover
                      isOpen={openPopover === "period"}
                      onClose={() => setOpenPopover(null)}
                      trigger={
                        <button
                          type="button"
                          onClick={() =>
                            setOpenPopover(openPopover === "period" ? null : "period")
                          }
                          className="flex h-8 items-center gap-1 rounded-l-md px-3 text-xs font-medium hover:bg-accent"
                        >
                          <span aria-hidden>📅</span>
                          {periodLabel(filters.period, dataYears)}
                          <span aria-hidden>▾</span>
                        </button>
                      }
                    >
                      <div className="flex flex-col gap-1">
                        {(
                          [
                            { mode: "max" as const, label: "Máximo" },
                            { mode: "ytd" as const, label: String(new Date().getFullYear()) },
                            { mode: "12m" as const, label: "Últimos 12 meses" },
                          ]
                        ).map((opt) => (
                          <button
                            key={opt.mode}
                            type="button"
                            onClick={() => {
                              setFilters((f) => ({ ...f, period: { mode: opt.mode } }));
                              setOpenPopover(null);
                            }}
                            className={cn(
                              "rounded px-2 py-1.5 text-left text-xs hover:bg-accent",
                              filters.period.mode === opt.mode ? "bg-accent font-medium" : "",
                            )}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </Popover>
                    <button
                      type="button"
                      onClick={() => {
                        const today = new Date();
                        const yyyy = today.getFullYear();
                        const mm = String(today.getMonth() + 1).padStart(2, "0");
                        const minYear = dataYears[0] ?? yyyy;
                        setFilters((f) => ({
                          ...f,
                          period: {
                            mode: "custom",
                            start: `${minYear}-01`,
                            end: `${yyyy}-${mm}`,
                          },
                        }));
                      }}
                      className="flex h-8 items-center rounded-r-md px-2 text-xs hover:bg-accent"
                      aria-label="Definir período personalizado"
                      title="Definir período personalizado"
                    >
                      ✎
                    </button>
                  </>
                )}
              </div>

              {/* Right group: Métrica + Fechar */}
              <div className="ml-auto flex items-center gap-2">
                <Popover
                  isOpen={openPopover === "metric"}
                  onClose={() => setOpenPopover(null)}
                  align="right"
                  trigger={
                    <button
                      type="button"
                      onClick={() =>
                        setOpenPopover(openPopover === "metric" ? null : "metric")
                      }
                      className="flex h-8 items-center gap-1 rounded-md border border-border bg-card px-3 text-xs font-medium hover:bg-accent"
                    >
                      <span aria-hidden>▦</span>
                      {filters.metric === "value" ? "Valor" : "Yield"}
                      <span aria-hidden>▾</span>
                    </button>
                  }
                >
                  <div className="flex flex-col gap-1">
                    {(
                      [
                        { mode: "value" as const, label: "Valor (R$)" },
                        { mode: "yield" as const, label: "Yield (%)" },
                      ]
                    ).map((opt) => (
                      <button
                        key={opt.mode}
                        type="button"
                        onClick={() => {
                          setFilters((f) => ({ ...f, metric: opt.mode }));
                          setOpenPopover(null);
                        }}
                        className={cn(
                          "rounded px-2 py-1.5 text-left text-xs hover:bg-accent",
                          filters.metric === opt.mode ? "bg-accent font-medium" : "",
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </Popover>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFilterBarOpen(false)}
                  aria-label="Fechar barra de filtros"
                >
                  ×
                </Button>
              </div>
            </>
          )}
        </div>
      </CardHeader>

      <CardContent className="px-0 pt-2">
        {yearRows.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-muted-foreground">
            Nenhum provento no período/filtros selecionados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="sticky left-0 z-10 w-20 bg-muted/40 px-2 py-2 text-left">Ano</th>
                  {MONTHS.map((m) => (
                    <th key={m} className="px-2 py-2 text-center">{m}</th>
                  ))}
                  <th className="px-2 py-2 text-center">x̄ Média</th>
                  <th className="px-2 py-2 text-center">Σ Total</th>
                  <th className="px-2 py-2 text-center">↗ Var</th>
                </tr>
              </thead>
              <tbody>
                {yearRows.map((row, idx) => {
                  const monthsFilled = row.months.filter((v) => v != null).length;
                  const prev = idx > 0 ? yearRows[idx - 1].total : 0;
                  const variancePrev = variation(row.total, prev);
                  const expanded = expandedYears.has(row.year);

                  return (
                    <YearRowRender
                      key={row.year}
                      row={row}
                      expanded={expanded}
                      maxMonthValue={maxMonthValue}
                      monthsFilled={monthsFilled}
                      variancePrev={variancePrev}
                      displayCellMain={displayCellMain}
                      displayTotal={displayTotal}
                      displayAverage={displayAverage}
                      onToggle={() =>
                        setExpandedYears((s) => {
                          const next = new Set(s);
                          if (next.has(row.year)) next.delete(row.year);
                          else next.add(row.year);
                          return next;
                        })
                      }
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Year row sub-component
// ---------------------------------------------------------------------------

function YearRowRender({
  row,
  expanded,
  maxMonthValue,
  monthsFilled,
  variancePrev,
  displayCellMain,
  displayTotal,
  displayAverage,
  onToggle,
}: {
  row: YearRow;
  expanded: boolean;
  maxMonthValue: number;
  monthsFilled: number;
  variancePrev: { pct: number | null; arrow: "up" | "down" | null };
  displayCellMain: (cents: number | null) => string;
  displayTotal: (cents: number) => string;
  displayAverage: (cents: number, months: number) => string;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="hover:bg-muted/20">
        <td className="sticky left-0 z-10 bg-card px-2 py-1 text-left font-medium">
          <button
            type="button"
            onClick={onToggle}
            className="inline-flex items-center gap-1 hover:underline"
            aria-expanded={expanded}
            aria-label={expanded ? "Recolher" : "Expandir por ativo"}
          >
            <span aria-hidden className="inline-block w-3 text-[10px] text-muted-foreground">
              {expanded ? "▼" : "▶"}
            </span>
            {row.year}
          </button>
        </td>
        {row.months.map((v, i) => (
          <td key={i} className="px-1 py-1">
            <div
              className={cn(
                "rounded-md px-2 py-1.5 text-center tabular-nums",
                heatmapClass(v ?? 0, maxMonthValue),
              )}
            >
              {displayCellMain(v) || <span className="text-muted-foreground/40">/</span>}
            </div>
          </td>
        ))}
        <td className="px-1 py-1">
          <div className="rounded-md bg-muted/40 px-2 py-1.5 text-center font-medium tabular-nums">
            {displayAverage(row.total, monthsFilled)}
          </div>
        </td>
        <td className="px-1 py-1">
          <div className="rounded-md bg-muted/60 px-2 py-1.5 text-center font-semibold tabular-nums">
            {displayTotal(row.total)}
          </div>
        </td>
        <td className="px-1 py-1">
          <div className="rounded-md bg-muted/40 px-2 py-1.5 text-center tabular-nums">
            {variancePrev.pct == null ? (
              <span className="text-muted-foreground/40">—</span>
            ) : (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 text-xs font-medium",
                  variancePrev.arrow === "up"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-amber-600 dark:text-amber-400",
                )}
              >
                {variancePrev.arrow === "up" ? "▲" : "▼"}{" "}
                {formatPercent(Math.abs(variancePrev.pct))}
              </span>
            )}
          </div>
        </td>
      </tr>

      {expanded
        ? Array.from(row.byAsset.values())
            .sort((a, b) => b.total - a.total)
            .map((asset) => {
              const filled = asset.months.filter((v) => v != null).length;
              return (
                <tr key={`${row.year}-${asset.assetCode}`} className="text-muted-foreground">
                  <td className="sticky left-0 z-10 bg-card px-2 py-0.5 pl-7 text-left text-[11px]">
                    {asset.assetCode}
                  </td>
                  {asset.months.map((v, i) => (
                    <td key={i} className="px-1 py-0.5">
                      <div
                        className={cn(
                          "rounded-md px-2 py-1 text-center tabular-nums text-[11px]",
                          heatmapClass(v ?? 0, maxMonthValue),
                        )}
                      >
                        {displayCellMain(v) || (
                          <span className="text-muted-foreground/30">·</span>
                        )}
                      </div>
                    </td>
                  ))}
                  <td className="px-1 py-0.5">
                    <div className="rounded-md bg-muted/30 px-2 py-1 text-center tabular-nums text-[11px]">
                      {displayAverage(asset.total, filled)}
                    </div>
                  </td>
                  <td className="px-1 py-0.5">
                    <div className="rounded-md bg-muted/50 px-2 py-1 text-center font-medium tabular-nums text-[11px]">
                      {displayTotal(asset.total)}
                    </div>
                  </td>
                  <td />
                </tr>
              );
            })
        : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Checkbox list (popover content)
// ---------------------------------------------------------------------------

function TickerPicker({
  options,
  selected,
  onPick,
}: {
  options: string[];
  selected: string;
  onPick: (ticker: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q) return options;
    return options.filter((t) => t.includes(q));
  }, [options, query]);

  return (
    <div className="flex w-[220px] flex-col gap-1">
      <Input
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Buscar ticker..."
        className="h-7 text-xs"
      />
      <button
        type="button"
        onClick={() => onPick("")}
        className={cn(
          "rounded px-2 py-1 text-left text-xs hover:bg-accent",
          selected === "" ? "bg-accent font-medium" : "",
        )}
      >
        Todos
      </button>
      <div className="max-h-[280px] overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-2 py-2 text-center text-xs text-muted-foreground">
            Nenhum ativo
          </div>
        ) : (
          filtered.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => onPick(t)}
              className={cn(
                "block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent",
                selected === t ? "bg-accent font-medium" : "",
              )}
            >
              {t}
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function CheckboxList({
  options,
  selected,
  onChange,
}: {
  options: { value: string; label: string }[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2 border-b border-border px-1 pb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
        <button
          type="button"
          className="hover:underline"
          onClick={() => onChange(new Set(options.map((o) => o.value)))}
        >
          Todas
        </button>
        <button
          type="button"
          className="hover:underline"
          onClick={() => onChange(new Set())}
        >
          Nenhuma
        </button>
      </div>
      {options.map((opt) => {
        const checked = selected.has(opt.value);
        return (
          <label
            key={opt.value}
            className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-accent"
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={() => {
                const next = new Set(selected);
                if (checked) next.delete(opt.value);
                else next.add(opt.value);
                onChange(next);
              }}
              className="h-3.5 w-3.5"
            />
            {opt.label}
          </label>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom period controls (Start / End dropdowns + clear)
// ---------------------------------------------------------------------------

function CustomPeriodControls({
  period,
  onChange,
  minYear,
  maxYear,
}: {
  period: Period;
  onChange: (p: Period) => void;
  minYear: number;
  maxYear: number;
}) {
  const [openSide, setOpenSide] = useState<"start" | "end" | null>(null);

  const fmt = (v?: string) =>
    v ? `${MONTHS[parseInt(v.slice(5, 7), 10) - 1]}/${v.slice(0, 4)}` : "—";

  return (
    <div className="flex items-center">
      <Popover
        isOpen={openSide === "start"}
        onClose={() => setOpenSide(null)}
        trigger={
          <button
            type="button"
            onClick={() => setOpenSide(openSide === "start" ? null : "start")}
            className="flex h-8 items-center gap-1 rounded-l-md px-3 text-xs hover:bg-accent"
          >
            Início: {fmt(period.start)}
          </button>
        }
      >
        <MonthPicker
          value={period.start}
          minYear={minYear}
          maxYear={maxYear}
          onPick={(ym) => {
            onChange({ ...period, start: ym });
            setOpenSide(null);
          }}
        />
      </Popover>
      <span className="h-6 w-px bg-border" />
      <Popover
        isOpen={openSide === "end"}
        onClose={() => setOpenSide(null)}
        trigger={
          <button
            type="button"
            onClick={() => setOpenSide(openSide === "end" ? null : "end")}
            className="flex h-8 items-center gap-1 px-3 text-xs hover:bg-accent"
          >
            Fim: {fmt(period.end)}
          </button>
        }
      >
        <MonthPicker
          value={period.end}
          minYear={minYear}
          maxYear={maxYear}
          onPick={(ym) => {
            onChange({ ...period, end: ym });
            setOpenSide(null);
          }}
        />
      </Popover>
      <button
        type="button"
        onClick={() => onChange({ mode: "max" })}
        className="flex h-8 items-center rounded-r-md px-2 text-xs text-muted-foreground hover:bg-accent"
        aria-label="Limpar período personalizado"
        title="Voltar para Máximo"
      >
        ×
      </button>
    </div>
  );
}
