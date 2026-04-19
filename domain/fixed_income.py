"""Fixed income (renda fixa) domain models.

This module describes individual brazilian fixed-income bank applications
(CDB, LCI, LCA) treated as standalone records. The ``FixedIncomePosition``
dataclass captures only contract data — gross/net values are always
recomputed by :mod:`domain.fixed_income_valuation` against today's date.

Design decisions for the V1 MVP
-------------------------------
* One application = one record. No batching, no fiscal grouping.
* Calculations are always performed against the *current* date supplied
  by the application clock (or ``date.today()`` by default).
* IOF is intentionally **out of scope** for this MVP and not subtracted
  from the net value. This is a deliberate simplification documented to
  the user in the UI.
* LCI/LCA for individuals (PF) are treated as IR-exempt.
* CDB PF uses the regressive IR table (see
  :mod:`domain.fixed_income_tax`).
* All monetary fields exposed by this dataclass are stored as integer
  cents (R$ 1,00 = 100), matching the convention used by the rest of
  the codebase (see ``domain/models.py``). High-precision decimal
  arithmetic is performed inside the valuation service and only
  rounded to cents at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Allowed values (V1 MVP)
# ---------------------------------------------------------------------------

#: Asset types supported in V1.
ASSET_TYPES: tuple[str, ...] = ("CDB", "LCI", "LCA")

#: Remuneration types supported in V1.
REMUNERATION_TYPES: tuple[str, ...] = ("PRE", "CDI_PERCENT")

#: Benchmarks supported in V1.
BENCHMARKS: tuple[str, ...] = ("NONE", "CDI")

#: Investor types supported in V1.
INVESTOR_TYPES: tuple[str, ...] = ("PF",)

#: Position lifecycle status values.
STATUSES: tuple[str, ...] = ("ACTIVE", "MATURED", "REDEEMED")


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


@dataclass
class FixedIncomePosition:
    """A single bank fixed-income application.

    All percentage fields are stored as plain ``float`` values expressed
    in *percent* (e.g. ``13.75`` means 13.75% per year, ``110.0`` means
    110% of the CDI). All monetary fields are stored as integer cents.
    """

    # Identification / classification ----------------------------------
    portfolio_id: str
    institution: str
    asset_type: str                 # CDB | LCI | LCA
    product_name: str
    remuneration_type: str          # PRE | CDI_PERCENT
    benchmark: str                  # NONE | CDI
    investor_type: str              # PF
    currency: str                   # BRL

    # Contract ---------------------------------------------------------
    application_date: str           # ISO 8601 YYYY-MM-DD
    maturity_date: str              # ISO 8601 YYYY-MM-DD
    principal_applied_brl: int      # cents

    # Optional contract details ----------------------------------------
    liquidity_label: str | None = None
    fixed_rate_annual_percent: float | None = None
    benchmark_percent: float | None = None

    # Optional importer/conference fields ------------------------------
    imported_gross_value_brl: int | None = None         # cents
    imported_net_value_brl: int | None = None           # cents
    imported_estimated_ir_brl: int | None = None        # cents
    valuation_reference_date: str | None = None         # ISO 8601 date
    notes: str | None = None

    # Lifecycle --------------------------------------------------------
    status: str = "ACTIVE"

    # Identity ---------------------------------------------------------
    id: int | None = None
    external_id: str | None = None
    import_job_id: int | None = None

    def __post_init__(self) -> None:
        if self.asset_type not in ASSET_TYPES:
            raise ValueError(
                f"Invalid asset_type '{self.asset_type}'. Allowed: {ASSET_TYPES}"
            )
        if self.remuneration_type not in REMUNERATION_TYPES:
            raise ValueError(
                f"Invalid remuneration_type '{self.remuneration_type}'. "
                f"Allowed: {REMUNERATION_TYPES}"
            )
        if self.benchmark not in BENCHMARKS:
            raise ValueError(
                f"Invalid benchmark '{self.benchmark}'. Allowed: {BENCHMARKS}"
            )
        if self.investor_type not in INVESTOR_TYPES:
            raise ValueError(
                f"Invalid investor_type '{self.investor_type}'. "
                f"Allowed: {INVESTOR_TYPES}"
            )
        if self.status not in STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Allowed: {STATUSES}"
            )
        if self.principal_applied_brl <= 0:
            raise ValueError("principal_applied_brl must be > 0")

        if self.remuneration_type == "PRE":
            if self.fixed_rate_annual_percent is None:
                raise ValueError(
                    "fixed_rate_annual_percent is required when remuneration_type=PRE"
                )
            if self.benchmark != "NONE":
                raise ValueError(
                    "benchmark must be NONE when remuneration_type=PRE"
                )
        elif self.remuneration_type == "CDI_PERCENT":
            if self.benchmark != "CDI":
                raise ValueError(
                    "benchmark must be CDI when remuneration_type=CDI_PERCENT"
                )
            if self.benchmark_percent is None:
                raise ValueError(
                    "benchmark_percent is required when remuneration_type=CDI_PERCENT"
                )


# ---------------------------------------------------------------------------
# Valuation result (returned by FixedIncomeValuationService)
# ---------------------------------------------------------------------------


@dataclass
class FixedIncomeValuation:
    """Output of the valuation service for a single position.

    Monetary fields are integer cents (BRL). The service computes them
    using high-precision :class:`~decimal.Decimal` arithmetic and only
    rounds to cents at the boundary (this dataclass).
    """

    position_id: int | None
    valuation_date: str             # ISO 8601 date the calculation refers to
    days_since_application: int
    gross_value_current_brl: int
    gross_income_current_brl: int
    estimated_ir_current_brl: int
    net_value_current_brl: int
    tax_bracket_current: str | None         # e.g. "22.5%" or "isento"
    is_complete: bool                       # False if e.g. CDI series is missing
    incomplete_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "valuation_date": self.valuation_date,
            "days_since_application": self.days_since_application,
            "gross_value_current_brl": self.gross_value_current_brl,
            "gross_income_current_brl": self.gross_income_current_brl,
            "estimated_ir_current_brl": self.estimated_ir_current_brl,
            "net_value_current_brl": self.net_value_current_brl,
            "tax_bracket_current": self.tax_bracket_current,
            "is_complete": self.is_complete,
            "incomplete_reason": self.incomplete_reason,
        }
