"""IRPF (DIRPF) report domain — pure business logic.

Builds a tax-reporting projection of `operations` + `positions` grouped by
the codes the Brazilian Receita Federal expects in the personal income-tax
declaration:

- Rendimentos Isentos: 09 (dividendos), 18 (bonificação), 99 (outros — FII/FIAGRO).
- Tributação Exclusiva: 10 (JCP líquido).
- Bens e Direitos: 03▷01 (ações), 07▷03 (FII), 07▷02 (FIAGRO),
  99▷07 (JCP a receber), 99▷99 (outros a receber).
"""

from domain.irpf.builder import IrpfReportBuilder
from domain.irpf.classifier import classify
from domain.irpf.discriminacao import format_discriminacao
from domain.irpf.models import (
    IrpfBemDireitoExtra,
    IrpfReport,
    IrpfRow,
    IrpfSection,
)

__all__ = [
    "IrpfBemDireitoExtra",
    "IrpfReport",
    "IrpfReportBuilder",
    "IrpfRow",
    "IrpfSection",
    "classify",
    "format_discriminacao",
]
