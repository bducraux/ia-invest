"""Dataclasses for the IRPF report payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

IrpfCategory = Literal["isento", "exclusivo", "bem_direito"]


@dataclass(frozen=True)
class IrpfBemDireitoExtra:
    """Extra fields present only in Bens e Direitos rows."""

    quantity: float
    avg_price_cents: int
    total_cents: int
    # Snapshot at 31/12 of the previous year (for the "Situação anterior" column).
    previous_total_cents: int = 0
    previous_quantity: float = 0.0


@dataclass
class IrpfRow:
    asset_code: str
    asset_name: str | None
    cnpj: str | None
    value_cents: int
    extra: IrpfBemDireitoExtra | None = None
    discriminacao: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class IrpfSection:
    code: str  # "09", "10", "03-01", "99-07", ...
    title: str
    category: IrpfCategory
    rows: list[IrpfRow] = field(default_factory=list)

    @property
    def total_cents(self) -> int:
        return sum(r.value_cents for r in self.rows)


@dataclass
class IrpfReport:
    portfolio_id: str
    base_year: int
    sections: list[IrpfSection]
    generated_at: datetime
    warnings: list[str] = field(default_factory=list)
