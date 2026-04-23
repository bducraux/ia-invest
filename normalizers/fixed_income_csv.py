"""CSV importer for brazilian fixed-income applications (V1 MVP).

The importer accepts a simplified snake_case CSV with one row per
application and converts each row into a
:class:`~domain.fixed_income.FixedIncomePosition`.

Required columns
----------------
- ``institution``
- ``asset_type``                (CDB | LCI | LCA)
- ``product_name``
- ``remuneration_type``         (PRE | CDI_PERCENT)
- ``application_date``          (ISO ``YYYY-MM-DD`` or ``DD/MM/YYYY``)
- ``maturity_date``             (same formats)
- ``application_value``         (must be > 0)

Conditionally required
----------------------
- ``fixed_rate_annual_percent`` — required iff ``remuneration_type == "PRE"``
- ``benchmark`` (= "CDI") and ``benchmark_percent`` —
  required iff ``remuneration_type == "CDI_PERCENT"``

Optional columns
----------------
- ``benchmark`` (defaults to ``NONE`` for PRE, ``CDI`` for CDI_PERCENT)
- ``liquidity_label``
- ``notes``

Investor type defaults to ``PF`` (V1 product decision).

Monetary cells are parsed via :class:`~decimal.Decimal` (never
``float``) and accept brazilian formatting (``"1.234,56"``) as well
as plain decimals.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Any

from domain.fixed_income import FixedIncomePosition
from normalizers.validator import parse_date

REQUIRED_COLUMNS: tuple[str, ...] = (
    "institution",
    "asset_type",
    "product_name",
    "remuneration_type",
    "application_date",
    "maturity_date",
    "application_value",
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "benchmark",
    "benchmark_percent",
    "fixed_rate_annual_percent",
    "liquidity_label",
    "notes",
)


@dataclass
class FixedIncomeCSVError:
    row_index: int | None
    message: str
    field: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class FixedIncomeCSVResult:
    valid: list[FixedIncomePosition] = field(default_factory=list)
    errors: list[FixedIncomeCSVError] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.errors)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _parse_decimal(raw: Any, field_name: str) -> Decimal:
    if raw is None:
        raise ValueError(f"{field_name} is required")
    text = str(raw).strip()
    if text == "":
        raise ValueError(f"{field_name} is required")

    # Strip currency markers
    text = text.replace("R$", "").replace("r$", "").strip()
    # Brazilian formatting: "1.234,56" -> "1234.56"
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} is not a valid number: {raw!r}") from exc


def _parse_brl_to_cents(raw: Any, field_name: str) -> int:
    value = _parse_decimal(raw, field_name)
    # Round half-even to cents.
    quantised = (value * Decimal(100)).quantize(Decimal("1"))
    return int(quantised)


def _parse_optional(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


class FixedIncomeCSVImporter:
    """Parses a CSV stream into :class:`FixedIncomePosition` records."""

    DEFAULT_INVESTOR_TYPE = "PF"
    DEFAULT_CURRENCY = "BRL"

    def parse_file(self, path: Path | str, portfolio_id: str) -> FixedIncomeCSVResult:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            return self.parse_stream(fh, portfolio_id)

    def parse_text(self, text: str, portfolio_id: str) -> FixedIncomeCSVResult:
        return self.parse_stream(io.StringIO(text), portfolio_id)

    def parse_stream(self, stream: IO[str], portfolio_id: str) -> FixedIncomeCSVResult:
        result = FixedIncomeCSVResult()

        # Sniff delimiter; default to comma on failure.
        sample = stream.read(2048)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)

        if reader.fieldnames is None:
            result.errors.append(
                FixedIncomeCSVError(row_index=None, message="CSV has no header row")
            )
            return result

        # Normalize headers (snake_case, lower).
        normalized_fields = [h.strip().lower() for h in reader.fieldnames if h]
        missing = [c for c in REQUIRED_COLUMNS if c not in normalized_fields]
        if missing:
            result.errors.append(
                FixedIncomeCSVError(
                    row_index=None,
                    message=f"Missing required column(s): {', '.join(missing)}",
                )
            )
            return result

        for row_index, raw_row in enumerate(reader):
            row = {
                (k.strip().lower() if k else ""): v
                for k, v in raw_row.items()
                if k is not None
            }
            try:
                position = self._row_to_position(row, portfolio_id)
                result.valid.append(position)
            except ValueError as exc:
                result.errors.append(
                    FixedIncomeCSVError(
                        row_index=row_index,
                        message=str(exc),
                        raw=row,
                    )
                )
        return result

    # ------------------------------------------------------------------

    def _row_to_position(
        self,
        row: dict[str, Any],
        portfolio_id: str,
    ) -> FixedIncomePosition:
        for required in REQUIRED_COLUMNS:
            if _parse_optional(row.get(required)) is None:
                raise ValueError(f"{required} is required")

        asset_type = str(row["asset_type"]).strip().upper()
        if asset_type not in ("CDB", "LCI", "LCA"):
            raise ValueError(
                f"asset_type must be one of CDB, LCI, LCA (got {asset_type!r})"
            )

        remuneration_type = str(row["remuneration_type"]).strip().upper()
        if remuneration_type not in ("PRE", "CDI_PERCENT"):
            raise ValueError(
                f"remuneration_type must be PRE or CDI_PERCENT (got {remuneration_type!r})"
            )

        # benchmark + percent fields, with validation per remuneration type.
        benchmark_raw = _parse_optional(row.get("benchmark"))
        benchmark_percent_raw = _parse_optional(row.get("benchmark_percent"))
        fixed_rate_raw = _parse_optional(row.get("fixed_rate_annual_percent"))

        if remuneration_type == "PRE":
            if fixed_rate_raw is None:
                raise ValueError(
                    "fixed_rate_annual_percent is required when remuneration_type=PRE"
                )
            benchmark = (benchmark_raw or "NONE").upper()
            if benchmark != "NONE":
                raise ValueError("benchmark must be NONE (or empty) when remuneration_type=PRE")
            fixed_rate = float(_parse_decimal(fixed_rate_raw, "fixed_rate_annual_percent"))
            benchmark_percent = None
        else:   # CDI_PERCENT
            benchmark = (benchmark_raw or "CDI").upper()
            if benchmark != "CDI":
                raise ValueError(
                    "benchmark must be CDI when remuneration_type=CDI_PERCENT"
                )
            if benchmark_percent_raw is None:
                raise ValueError(
                    "benchmark_percent is required when remuneration_type=CDI_PERCENT"
                )
            benchmark_percent = float(
                _parse_decimal(benchmark_percent_raw, "benchmark_percent")
            )
            fixed_rate = (
                float(_parse_decimal(fixed_rate_raw, "fixed_rate_annual_percent"))
                if fixed_rate_raw is not None
                else None
            )

        # Dates — parse_date raises ValueError with a clear message.
        application_date = parse_date(row.get("application_date"))
        maturity_date = parse_date(row.get("maturity_date"))
        principal_cents = _parse_brl_to_cents(
            row["application_value"], "application_value"
        )
        if principal_cents <= 0:
            raise ValueError("application_value must be > 0")

        return FixedIncomePosition(
            portfolio_id=portfolio_id,
            institution=str(row["institution"]).strip(),
            asset_type=asset_type,
            product_name=str(row["product_name"]).strip(),
            remuneration_type=remuneration_type,
            benchmark=benchmark,
            investor_type=self.DEFAULT_INVESTOR_TYPE,
            currency=self.DEFAULT_CURRENCY,
            application_date=application_date,
            maturity_date=maturity_date,
            principal_applied_brl=principal_cents,
            liquidity_label=_parse_optional(row.get("liquidity_label")),
            fixed_rate_annual_percent=fixed_rate,
            benchmark_percent=benchmark_percent,
            notes=_parse_optional(row.get("notes")),
        )
