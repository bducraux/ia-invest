"""Snapshot model for IBM previdencia statements.

This domain entity stores the latest imported snapshot for a previdencia asset.
The import policy is month-based: older statement months cannot overwrite newer
snapshots for the same portfolio/asset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PrevidenciaSnapshot:
    portfolio_id: str
    asset_code: str
    product_name: str
    quantity: float
    unit_price_cents: int
    market_value_cents: int
    period_month: str  # YYYY-MM
    period_start_date: str | None = None
    period_end_date: str | None = None
    source_file: str | None = None
    import_job_id: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative")
        if self.unit_price_cents < 0:
            raise ValueError("unit_price_cents cannot be negative")
        if self.market_value_cents < 0:
            raise ValueError("market_value_cents cannot be negative")
        if len(self.period_month) != 7 or self.period_month[4] != "-":
            raise ValueError("period_month must be in YYYY-MM format")
