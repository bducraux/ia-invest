"""Manual XLSX extractor for B3 (Brazilian equity) portfolio bootstrap files."""

from __future__ import annotations

from extractors.manual_xlsx_base import BaseManualXlsxExtractor


class ManualXlsxB3Extractor(BaseManualXlsxExtractor):
    """Extracts manually-prepared XLSX files for B3 portfolios."""

    source_type = "manual_xlsx_b3"
    external_id_prefix = "manual_xlsx"
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
