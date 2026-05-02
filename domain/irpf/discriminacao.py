"""Pure formatters for IRPF "Discriminação" strings (Bens e Direitos).

Reference output (from the user spec):

    278 cotas SAPR11 CIA SANEAMENTO DO PARANA - SANEPAR.
    Preço médio de 27,73 totalizando 7.709,43

Numbers use Brazilian formatting (comma decimal, dot thousands), no currency
symbol. Rounding follows Python's default ``round`` for the integer
quantity column.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal


def _format_quantity(quantity: float) -> str:
    """Render quantity as integer when whole, otherwise pt-BR decimal."""
    if float(quantity).is_integer():
        return f"{int(quantity)}"
    # Up to 8 decimals (crypto-friendly), strip trailing zeros, BR comma.
    text = f"{quantity:.8f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _format_brl_amount(cents: int) -> str:
    """Format integer cents as ``1.234,56`` (no currency prefix)."""
    decimal = (Decimal(int(cents)) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )
    integer_part, _, fractional = f"{decimal:.2f}".partition(".")
    sign = ""
    if integer_part.startswith("-"):
        sign = "-"
        integer_part = integer_part[1:]
    # Insert thousand separators (dots) every 3 digits.
    rev = integer_part[::-1]
    grouped = ".".join(rev[i : i + 3] for i in range(0, len(rev), 3))[::-1]
    return f"{sign}{grouped},{fractional}"


def format_discriminacao(
    asset_class_irpf: str,
    *,
    asset_code: str,
    asset_name: str | None,
    quantity: float,
    avg_price_cents: int,
    total_cents: int,
) -> str:
    """Generate the discriminação string for a Bens e Direitos row."""
    cls = (asset_class_irpf or "").lower()
    qty_text = _format_quantity(quantity)
    qty_int = int(quantity) if float(quantity).is_integer() else None

    if cls == "acao":
        unit = "ação" if qty_int == 1 else "ações"
    elif cls in {"fii", "fiagro"}:
        unit = "cota" if qty_int == 1 else "cotas"
    else:
        unit = "unidade" if qty_int == 1 else "unidades"

    name_part = f" {asset_name}" if asset_name else ""
    pm_text = _format_brl_amount(avg_price_cents)
    total_text = _format_brl_amount(total_cents)

    return (
        f"{qty_text} {unit} {asset_code}{name_part}. "
        f"Preço médio de {pm_text} totalizando {total_text}"
    )
