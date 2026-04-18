"""Gorila XLSX extractor for Brazilian equity/fixed-income portfolios."""

from __future__ import annotations

from extractors.gorila_base import BaseGorilaXlsxExtractor


class GorilaB3XlsxExtractor(BaseGorilaXlsxExtractor):
    """Extracts Gorila XLSX exports for B3 portfolios."""

    source_type = "gorila_b3_xlsx"
    operation_type_map = {
        "compra": "buy",
        "venda": "sell",
        "transferência de custódia": "transfer_in",
        "transferencia de custodia": "transfer_in",
        "ajustes de posição inicial": "transfer_in",
        "ajustes de posicao inicial": "transfer_in",
        "bonificação": "transfer_in",
        "bonificacao": "transfer_in",
        "desdobramento": "transfer_in",
    }
