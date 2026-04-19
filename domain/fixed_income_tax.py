"""Tax service for brazilian fixed-income applications (V1 MVP).

Rules implemented:

* **CDB PF — IR regressivo sobre o rendimento bruto:**

  =====================  ==========
  Days since application  IR rate
  =====================  ==========
  0 .. 180                22.5%
  181 .. 360              20.0%
  361 .. 720              17.5%
  > 720                   15.0%
  =====================  ==========

* **LCI / LCA PF:** isento de IR. ``estimated_ir = 0`` and
  ``net_value = gross_value``.

* **IOF:** intentionally **ignored** in the V1 MVP. This is a deliberate
  simplification documented to the user. The service exposes a hook
  (:meth:`FixedIncomeTaxService.calculate_iof`) returning ``Decimal(0)``
  so future versions can override it without touching the rest of the
  pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# IR table for CDB / PF (days_min_inclusive, days_max_inclusive_or_None, rate)
_CDB_PF_IR_TABLE: Final[tuple[tuple[int, int | None, Decimal], ...]] = (
    (0, 180, Decimal("0.225")),
    (181, 360, Decimal("0.20")),
    (361, 720, Decimal("0.175")),
    (721, None, Decimal("0.15")),
)


@dataclass(frozen=True)
class IRRate:
    """A taxation outcome lookup result."""

    rate: Decimal           # e.g. Decimal("0.225") for 22.5%
    label: str              # e.g. "22.5%" or "isento"


class FixedIncomeTaxService:
    """Pure tax calculator for brazilian fixed-income (V1 MVP)."""

    EXEMPT: Final[IRRate] = IRRate(rate=Decimal("0"), label="isento")

    def get_ir_rate(
        self,
        asset_type: str,
        investor_type: str,
        days_since_application: int,
    ) -> IRRate:
        """Return the IR rate that applies if redeemed today.

        ``days_since_application`` must be ``>= 0``.
        """
        if days_since_application < 0:
            raise ValueError("days_since_application must be >= 0")

        asset = asset_type.upper()
        investor = investor_type.upper()

        if asset in ("LCI", "LCA") and investor == "PF":
            return self.EXEMPT

        if asset == "CDB" and investor == "PF":
            for lo, hi, rate in _CDB_PF_IR_TABLE:
                if days_since_application >= lo and (hi is None or days_since_application <= hi):
                    label = f"{(rate * 100).normalize():f}%"
                    return IRRate(rate=rate, label=label)

        raise ValueError(
            f"Unsupported (asset_type, investor_type) combination: "
            f"({asset_type}, {investor_type})"
        )

    def calculate_estimated_ir(
        self,
        asset_type: str,
        investor_type: str,
        days_since_application: int,
        gross_income: Decimal,
    ) -> Decimal:
        """Return the IR amount due over the gross income (in BRL, Decimal).

        Negative gross_income is clamped to 0 (no IR refund on losses).
        """
        if gross_income <= Decimal("0"):
            return Decimal("0")
        ir = self.get_ir_rate(asset_type, investor_type, days_since_application)
        return gross_income * ir.rate

    def calculate_iof(
        self,
        asset_type: str,            # noqa: ARG002 — V1 ignores asset_type
        investor_type: str,         # noqa: ARG002 — V1 ignores investor_type
        days_since_application: int,    # noqa: ARG002
        gross_income: Decimal,          # noqa: ARG002
    ) -> Decimal:
        """IOF placeholder — intentionally returns zero for the V1 MVP.

        This method exists so that future versions can plug in the
        regressive IOF table (incidence in the first 30 days) without
        changing the rest of the calculation pipeline.
        """
        return Decimal("0")
