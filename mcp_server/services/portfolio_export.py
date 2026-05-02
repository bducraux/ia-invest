"""Portfolio export service.

Generates CSV snapshots of all data currently stored in SQLite for a given
portfolio. The output files are placed under ``portfolios/<id>/exports/`` and
are designed to be re-importable in case of a full database wipe.

Two CSVs may be generated, depending on what the portfolio actually contains:

* ``operations__<timestamp>.csv`` — one row per row of the ``operations`` table
  (including binance quote-leg rows). Re-importable through the
  ``ia_invest_export_csv`` source type.
* ``fixed_income__<timestamp>.csv`` — one row per ``fixed_income_positions``
  row. Compatible with the existing ``fixed_income_csv`` importer (same
  required columns), so it can be dropped back into ``inbox/`` to rebuild
  the renda-fixa portfolio.
* ``previdencia__<timestamp>.csv`` — one row per ``previdencia_snapshots``
  history entry. Re-importable through the
  ``ia_invest_previdencia_export_csv`` source type (auto-detected by
  header signature so disaster recovery does not require editing
  ``portfolio.yml``).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from domain.fixed_income import FixedIncomePosition
from domain.previdencia import PrevidenciaSnapshot
from storage.repository.fixed_income import FixedIncomePositionRepository
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository

OPERATIONS_HEADER: tuple[str, ...] = (
    # Identification
    "source",
    "external_id",
    # Asset
    "asset_code",
    "asset_type",
    "asset_name",
    # Operation
    "operation_type",
    "operation_date",
    "settlement_date",
    # Financials (BRL)
    "quantity",
    "unit_price",
    "gross_value",
    "fees",
    "net_value",
    # Multi-currency snapshot (informational on re-import)
    "trade_currency",
    "unit_price_native",
    "gross_value_native",
    "fees_native",
    "fx_rate_at_trade",
    "fx_rate_source",
    # Metadata
    "broker",
    "account",
    "notes",
)

FIXED_INCOME_HEADER: tuple[str, ...] = (
    "institution",
    "asset_type",
    "product_name",
    "remuneration_type",
    "benchmark",
    "benchmark_percent",
    "fixed_rate_annual_percent",
    "application_date",
    "maturity_date",
    "application_value",
    "liquidity_label",
    "notes",
)

PREVIDENCIA_HEADER: tuple[str, ...] = (
    "asset_code",
    "product_name",
    "period_month",
    "period_start_date",
    "period_end_date",
    "quantity",
    "unit_price",
    "market_value",
    "source_file",
)


@dataclass
class PortfolioExportResult:
    portfolio_id: str
    output_dir: Path
    files: list[dict[str, object]] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)


def _cents_to_decimal_str(cents: int) -> str:
    """Render integer cents as a plain decimal string ``123456`` -> ``1234.56``.

    The CSV importer parses these back into integer cents via
    ``parse_monetary_cents`` / ``Decimal``.
    """
    if cents == 0:
        return "0"
    sign = "-" if cents < 0 else ""
    abs_cents = abs(int(cents))
    reais, centavos = divmod(abs_cents, 100)
    return f"{sign}{reais}.{centavos:02d}"


def _format_quantity(quantity: float) -> str:
    """Render a quantity preserving precision but without scientific notation."""
    if quantity == 0:
        return "0"
    # ``Decimal(str(...))`` keeps the textual form chosen by Python's repr,
    # which avoids ``1e-08`` style outputs for the small crypto amounts.
    return format(Decimal(repr(quantity)).normalize(), "f")


def _operations_row(row: dict[str, object]) -> dict[str, str]:
    """Convert an ``operations`` table row into the export CSV shape.

    The exported ``unit_price`` / ``gross_value`` / ``fees`` are already
    BRL cents (post-FX), so we force ``trade_currency=BRL`` on the way
    out. The native amounts and FX snapshot remain as informational
    columns: :class:`OperationNormalizer` ignores them when
    ``trade_currency == 'BRL'`` and re-derives them from the BRL values.
    """
    out: dict[str, str] = {}
    for col in OPERATIONS_HEADER:
        value = row.get(col)
        if col == "trade_currency":
            # Always re-import as BRL because the BRL columns are the
            # consolidated source of truth in the database.
            out[col] = "BRL"
            continue
        if value is None:
            out[col] = ""
            continue
        if col == "quantity":
            out[col] = _format_quantity(float(value))
        elif col in {
            "unit_price",
            "gross_value",
            "fees",
            "net_value",
            "unit_price_native",
            "gross_value_native",
            "fees_native",
        }:
            out[col] = _cents_to_decimal_str(int(value))
        else:
            out[col] = str(value)
    return out


def _previdencia_row(snapshot: PrevidenciaSnapshot) -> dict[str, str]:
    return {
        "asset_code": snapshot.asset_code,
        "product_name": snapshot.product_name,
        "period_month": snapshot.period_month,
        "period_start_date": snapshot.period_start_date or "",
        "period_end_date": snapshot.period_end_date or "",
        "quantity": _format_quantity(snapshot.quantity),
        "unit_price": _cents_to_decimal_str(snapshot.unit_price_cents),
        "market_value": _cents_to_decimal_str(snapshot.market_value_cents),
        "source_file": snapshot.source_file or "",
    }


def _fixed_income_row(position: FixedIncomePosition) -> dict[str, str]:
    return {
        "institution": position.institution,
        "asset_type": position.asset_type,
        "product_name": position.product_name,
        "remuneration_type": position.remuneration_type,
        "benchmark": position.benchmark,
        "benchmark_percent": (
            "" if position.benchmark_percent is None
            else format(Decimal(repr(position.benchmark_percent)).normalize(), "f")
        ),
        "fixed_rate_annual_percent": (
            "" if position.fixed_rate_annual_percent is None
            else format(Decimal(repr(position.fixed_rate_annual_percent)).normalize(), "f")
        ),
        "application_date": position.application_date,
        "maturity_date": position.maturity_date,
        "application_value": _cents_to_decimal_str(position.principal_applied_brl),
        "liquidity_label": position.liquidity_label or "",
        "notes": position.notes or "",
    }


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


class PortfolioExportService:
    """Builds the per-portfolio export bundle."""

    def __init__(
        self,
        *,
        operation_repo: OperationRepository,
        fixed_income_repo: FixedIncomePositionRepository,
        portfolio_repo: PortfolioRepository,
        previdencia_repo: PrevidenciaSnapshotRepository | None = None,
        portfolios_root: Path = Path("portfolios"),
    ) -> None:
        self._operation_repo = operation_repo
        self._fixed_income_repo = fixed_income_repo
        self._portfolio_repo = portfolio_repo
        self._previdencia_repo = previdencia_repo
        self._portfolios_root = portfolios_root

    def export(self, portfolio_id: str) -> PortfolioExportResult:
        portfolio = self._portfolio_repo.get(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio '{portfolio_id}' not found")

        owner_id = portfolio.owner_id or "default"
        slug = portfolio.slug or portfolio_id
        output_dir = self._portfolios_root / owner_id / slug / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)

        result = PortfolioExportResult(
            portfolio_id=portfolio_id, output_dir=output_dir
        )
        timestamp = _utc_timestamp()

        # --- operations --------------------------------------------------
        operations = self._operation_repo.list_all_by_portfolio(portfolio_id)
        if operations:
            ops_path = output_dir / f"operations__{timestamp}.csv"
            with ops_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(OPERATIONS_HEADER))
                writer.writeheader()
                for row in operations:
                    writer.writerow(_operations_row(row))
            result.files.append({
                "kind": "operations",
                "path": str(ops_path),
                "rows": len(operations),
            })

        # --- fixed income ------------------------------------------------
        fi_positions = self._fixed_income_repo.list_by_portfolio(portfolio_id)
        if fi_positions:
            fi_path = output_dir / f"fixed_income__{timestamp}.csv"
            with fi_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(FIXED_INCOME_HEADER))
                writer.writeheader()
                for pos in fi_positions:
                    writer.writerow(_fixed_income_row(pos))
            result.files.append({
                "kind": "fixed_income",
                "path": str(fi_path),
                "rows": len(fi_positions),
            })

        # --- previdência -------------------------------------------------
        if self._previdencia_repo is not None:
            snapshots = self._previdencia_repo.list_history(portfolio_id)
            if snapshots:
                prev_path = output_dir / f"previdencia__{timestamp}.csv"
                with prev_path.open("w", encoding="utf-8", newline="") as fh:
                    writer = csv.DictWriter(
                        fh, fieldnames=list(PREVIDENCIA_HEADER)
                    )
                    writer.writeheader()
                    for snapshot in snapshots:
                        writer.writerow(_previdencia_row(snapshot))
                result.files.append({
                    "kind": "previdencia",
                    "path": str(prev_path),
                    "rows": len(snapshots),
                })

        return result
