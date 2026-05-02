"""Pure mapping (asset_class_irpf, operation_type) → DIRPF section.

The classifier returns a stable identifier for each section. The builder is
then responsible for grouping rows under the matching `IrpfSection`.

Section identifiers used:

- ``09``        — Rendimentos Isentos: lucros e dividendos recebidos (ações).
- ``10``        — Tributação Exclusiva/Definitiva: JCP (líquido).
- ``18``        — Rendimentos Isentos: incorporação de reservas / bonificação.
- ``99``        — Rendimentos Isentos: outros (FII/FIAGRO).
- ``03-01``     — Bens e Direitos: ações.
- ``07-03``     — Bens e Direitos: Fundos Imobiliários (FII).
- ``07-02``     — Bens e Direitos: FIAGRO.
- ``99-07``     — Bens e Direitos: JCP a receber.
- ``99-99``     — Bens e Direitos: outros bens e direitos a receber.
"""

from __future__ import annotations

from typing import Literal

AssetClassIrpf = Literal["acao", "fii", "fiagro", "bdr", "etf"]
ProventoOpType = Literal["dividend", "jcp", "rendimento", "split_bonus"]


def classify(asset_class_irpf: str | None, operation_type: str) -> str | None:
    """Map ``(asset_class_irpf, operation_type)`` to a DIRPF section code.

    Returns ``None`` when the combination falls outside V1 scope (e.g. JCP on
    a FII — not legal — or any operation on a class not yet supported like
    BDR/ETF).
    """
    cls = (asset_class_irpf or "").lower()
    op = (operation_type or "").lower()

    if op == "dividend":
        if cls == "acao":
            return "09"
        if cls in {"fii", "fiagro"}:
            return "99"
        return None

    if op == "rendimento":
        # `rendimento` is the canonical FII/FIAGRO income type.
        if cls in {"fii", "fiagro"}:
            return "99"
        return None

    if op == "jcp":
        if cls == "acao":
            return "10"
        return None

    if op == "split_bonus":
        if cls == "acao":
            return "18"
        return None

    return None


def bem_direito_section(asset_class_irpf: str | None) -> str | None:
    """Return the Bens e Direitos section code for an asset class."""
    cls = (asset_class_irpf or "").lower()
    if cls == "acao":
        return "03-01"
    if cls == "fii":
        return "07-03"
    if cls == "fiagro":
        return "07-02"
    return None


SECTION_TITLES: dict[str, str] = {
    "09": "Lucros e dividendos recebidos",
    "10": "Juros sobre Capital Próprio (JCP)",
    "18": "Incorporação de reservas ao capital / Bonificação em ações",
    "99": "Outros rendimentos",
    "03-01": "Ações",
    "07-03": "Fundos Imobiliários (FII)",
    "07-02": "Fundos de Investimento nas Cadeias Produtivas Agroindustriais (FIAGRO)",
    "99-07": "Juros sobre capital próprio a receber",
    "99-99": "Outros bens e direitos a receber",
}

SECTION_CATEGORIES: dict[str, str] = {
    "09": "isento",
    "18": "isento",
    "99": "isento",
    "10": "exclusivo",
    "03-01": "bem_direito",
    "07-03": "bem_direito",
    "07-02": "bem_direito",
    "99-07": "bem_direito",
    "99-99": "bem_direito",
}
