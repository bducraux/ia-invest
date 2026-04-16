"""Field validation helpers for normalizers."""

from __future__ import annotations

import re
from datetime import datetime

_OPERATION_TYPES = {
    "buy", "sell", "dividend", "jcp", "rendimento", "amortization",
    "split", "split_bonus", "merge", "transfer_in", "transfer_out",
    "subscription", "redemption",
}

_ASSET_TYPES = {
    "stock", "fii", "etf", "bdr", "bond", "treasury", "crypto",
    "international", "option", "fund",
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
]


def parse_date(value: str | None) -> str:
    """Parse a date string into ISO 8601 (YYYY-MM-DD) format.

    Raises:
        ValueError: if the value is empty or cannot be parsed.
    """
    if not value or not str(value).strip():
        raise ValueError("Date is required and cannot be empty.")

    raw = str(value).strip()
    # Handle datetime strings (take date part only)
    raw = raw[:10] if len(raw) > 10 else raw

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise ValueError(f"Unrecognised date format: '{value}'")


def parse_quantity(value: str | float | int | None) -> float:
    """Parse a quantity value, handling Brazilian number formatting.

    Raises:
        ValueError: if value is empty or non-numeric.
    """
    if value is None or str(value).strip() == "":
        raise ValueError("Quantity is required.")

    raw = str(value).strip()
    # Remove thousand separators and normalise decimal separator
    if "," in raw and "." in raw:
        # e.g. "1.234,56" → "1234.56"
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        # e.g. "1234,56" → "1234.56"
        raw = raw.replace(",", ".")

    try:
        qty = float(raw)
    except ValueError as err:
        raise ValueError(f"Cannot parse quantity: '{value}'") from err

    if qty < 0:
        raise ValueError(f"Quantity must not be negative: {qty}")

    return qty


def parse_monetary_cents(value: str | float | int | None, field: str = "value") -> int:
    """Parse a monetary value string into integer cents.

    Handles Brazilian (1.234,56) and US (1,234.56) formatting.

    Raises:
        ValueError: if value cannot be parsed as a number.
    """
    if value is None or str(value).strip() == "":
        return 0

    raw = str(value).strip()
    # Remove currency symbols and spaces
    raw = re.sub(r"[R$\s]", "", raw)

    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")

    try:
        amount = float(raw)
    except ValueError as err:
        raise ValueError(f"Cannot parse monetary {field}: '{value}'") from err

    return round(amount * 100)


def normalise_operation_type(value: str | None) -> str:
    """Normalise an operation type string to a canonical value.

    Raises:
        ValueError: if the value is empty or unrecognised.
    """
    if not value or not str(value).strip():
        raise ValueError("Operation type is required.")

    raw = str(value).strip().lower()

    _aliases: dict[str, str] = {
        "compra": "buy",
        "c": "buy",
        "venda": "sell",
        "v": "sell",
        "dividendo": "dividend",
        "div": "dividend",
        "jcp": "jcp",
        "jscp": "jcp",
        "rendimento": "rendimento",
        "bonificação": "split_bonus",
        "bonificacao": "split_bonus",
        "desdobramento": "split",
        "grupamento": "merge",
        "transferência entrada": "transfer_in",
        "transferencia entrada": "transfer_in",
        "transferência saída": "transfer_out",
        "transferencia saida": "transfer_out",
        "subscrição": "subscription",
        "subscricao": "subscription",
        "resgate": "redemption",
        "amortização": "amortization",
        "amortizacao": "amortization",
    }

    canonical = _aliases.get(raw, raw)

    if canonical not in _OPERATION_TYPES:
        raise ValueError(
            f"Unrecognised operation type: '{value}'. "
            f"Allowed: {sorted(_OPERATION_TYPES)}"
        )

    return canonical


def infer_asset_type(asset_code: str) -> str:
    """Heuristically infer asset type from a Brazilian asset code.

    This is a best-effort inference; portfolio rules will override if needed.
    """
    code = asset_code.upper().strip()

    if len(code) >= 5 and code[-2:] in {"11"}:
        return "fii"  # e.g. HGLG11, XPML11
    if len(code) >= 5 and code[:5] in {"NTNB", "NTNF", "LTN0", "LFT0"}:
        return "treasury"
    if len(code) == 6 and code[-2:] in {"34", "35"}:
        return "bdr"  # e.g. AAPL34, MSFT35 — BDR check before generic stock
    if len(code) in {5, 6} and code[-1] in {"3", "4", "5", "6"}:
        return "stock"

    return "stock"  # default fallback
