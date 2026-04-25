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
        result = self.config.get("rules", {}).get("allowed_asset_types", [])
        return list(result)

    @property
    def deduplicate_by(self) -> list[str]:
        if self.config is None:
            return ["source", "external_id", "operation_date", "asset_code", "operation_type"]
        result = self.config.get("import", {}).get(
            "deduplicate_by",
            ["source", "external_id", "operation_date", "asset_code", "operation_type"],
        )
        return list(result)

    @property
    def move_processed_files(self) -> bool:
        if self.config is None:
            return True
        return bool(self.config.get("import", {}).get("move_processed_files", True))


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
    unit_price: int                # cents (in BRL after FX conversion)
    gross_value: int               # cents (in BRL after FX conversion)
    fees: int = 0                  # cents (in BRL after FX conversion)
    net_value: int = 0             # cents (in BRL)
    external_id: str | None = None
    asset_name: str | None = None
    settlement_date: str | None = None
    broker: str | None = None
    account: str | None = None
    notes: str | None = None
    raw_data: dict[str, Any] | None = None
    import_job_id: int | None = None
    # Multi-currency: native amounts in trade_currency cents + FX snapshot.
    trade_currency: str = "BRL"
    unit_price_native: int = 0
    gross_value_native: int = 0
    fees_native: int = 0
    fx_rate_at_trade: str | None = None
    fx_rate_source: str | None = None

    def __post_init__(self) -> None:
        if self.net_value == 0:
            # Default: buy costs money (negative), sell earns money (positive)
            if self.operation_type in ("buy", "transfer_in"):
                self.net_value = -(self.gross_value + self.fees)
            else:
                self.net_value = self.gross_value - self.fees
        # Backfill native fields for BRL trades so storage stays consistent.
        if self.trade_currency == "BRL":
            if self.unit_price_native == 0:
                self.unit_price_native = self.unit_price
            if self.gross_value_native == 0:
                self.gross_value_native = self.gross_value
            if self.fees_native == 0:
                self.fees_native = self.fees
            if self.fx_rate_at_trade is None:
                self.fx_rate_at_trade = "1"
            if self.fx_rate_source is None:
                self.fx_rate_source = "native_brl"


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
