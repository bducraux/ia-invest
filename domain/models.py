"""Domain models — canonical data structures for IA-Invest.

All monetary values are stored and operated on as integer cents (100 = R$ 1.00)
to avoid floating-point rounding errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@dataclass
class Portfolio:
    id: str
    name: str
    description: str | None = None
    base_currency: str = "BRL"
    status: str = "active"
    config: dict[str, Any] | None = None

    @property
    def allowed_asset_types(self) -> list[str]:
        if self.config is None:
            return []
        return self.config.get("rules", {}).get("allowed_asset_types", [])

    @property
    def deduplicate_by(self) -> list[str]:
        if self.config is None:
            return ["source", "external_id", "operation_date", "asset_code", "operation_type"]
        return self.config.get("import", {}).get(
            "deduplicate_by",
            ["source", "external_id", "operation_date", "asset_code", "operation_type"],
        )

    @property
    def move_processed_files(self) -> bool:
        if self.config is None:
            return True
        return self.config.get("import", {}).get("move_processed_files", True)


# ---------------------------------------------------------------------------
# Operation
# ---------------------------------------------------------------------------

@dataclass
class Operation:
    portfolio_id: str
    source: str
    asset_code: str
    asset_type: str
    operation_type: str
    operation_date: str            # ISO 8601 YYYY-MM-DD
    quantity: float
    unit_price: int                # cents
    gross_value: int               # cents
    fees: int = 0                  # cents
    net_value: int = 0             # cents
    external_id: str | None = None
    asset_name: str | None = None
    settlement_date: str | None = None
    broker: str | None = None
    account: str | None = None
    notes: str | None = None
    raw_data: dict[str, Any] | None = None
    import_job_id: int | None = None

    def __post_init__(self) -> None:
        if self.net_value == 0:
            # Default: buy costs money (negative), sell earns money (positive)
            if self.operation_type in ("buy", "transfer_in"):
                self.net_value = -(self.gross_value + self.fees)
            else:
                self.net_value = self.gross_value - self.fees


# ---------------------------------------------------------------------------
# Position (materialised / cached)
# ---------------------------------------------------------------------------

@dataclass
class Position:
    portfolio_id: str
    asset_code: str
    asset_type: str
    quantity: float = 0.0
    avg_price: int = 0             # cents per unit
    total_cost: int = 0            # cents
    realized_pnl: int = 0         # cents
    dividends: int = 0             # cents
    asset_name: str | None = None
    first_operation_date: str | None = None
    last_operation_date: str | None = None


# ---------------------------------------------------------------------------
# Import job / audit
# ---------------------------------------------------------------------------

@dataclass
class ImportJob:
    portfolio_id: str
    source_type: str
    file_name: str
    file_hash: str | None = None
    file_path: str | None = None
    status: str = "pending"
    id: int | None = None


@dataclass
class NormalizationError:
    row_index: int | None
    error_type: str
    message: str
    field: str | None = None
    raw_data: dict[str, Any] | None = None


@dataclass
class NormalizationResult:
    valid: list[Operation] = field(default_factory=list)
    errors: list[NormalizationError] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
