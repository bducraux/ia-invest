"""Manual dividends CSV extractor.

Generic format for manually-curated provento histories — dividendos, JCP and
rendimentos — that the user couldn't (or doesn't want to) source from the
B3 Movimentação export. Useful for backfilling years prior to the user's
B3 history availability or for one-off events the broker missed.

Expected CSV columns (case-insensitive, exact names):

    data_pagamento, ticker, tipo, quantidade, valor_total

Where:
    - ``data_pagamento`` is ISO 8601 (YYYY-MM-DD).
    - ``tipo`` is one of ``dividendo``, ``jcp``, ``rendimento``.
    - ``valor_total`` is the **gross** BRL amount (qty × valor_por_cota).
      For JCP we estimate net = gross × 0.85 (15% IR) since the source
      typically only carries gross. Dividendo and Rendimento have no IR.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

#: CSV → canonical operation type
_TIPO_MAP: dict[str, str] = {
    "dividendo": "dividend",
    "jcp": "jcp",
    "rendimento": "rendimento",
}

_REQUIRED_COLUMNS: set[str] = {
    "data_pagamento",
    "ticker",
    "tipo",
    "quantidade",
    "valor_total",
}

#: Estimated IR rate withheld at source on JCP for individuals.
_JCP_IR_RATE = 0.15


def _parse_number(value: str) -> float | None:
    raw = (value or "").strip().replace("R$", "").replace("\xa0", " ").strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _to_cents(value: float | None) -> int:
    if value is None:
        return 0
    return int(round(value * 100))


class ManualDividendsCsvExtractor(BaseExtractor):
    """Parses a curated provento history CSV with 5 columns."""

    source_type = "manual_dividends_csv"

    EXTRACTOR_VERSION = 1

    def can_handle(self, file_path: Path) -> bool:
        if file_path.suffix.lower() != ".csv":
            return False
        try:
            with file_path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                header = [h.strip().lower() for h in next(reader, [])]
        except Exception:  # noqa: BLE001
            return False
        return _REQUIRED_COLUMNS.issubset(set(header))

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=self.source_type)
        try:
            with file_path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                {
                    "row_index": None,
                    "error_type": "parsing",
                    "message": f"Could not read manual dividends CSV: {exc}",
                }
            )
            return result

        for row_index, raw in enumerate(rows, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}

            tipo_raw = row.get("tipo", "").lower()
            operation_type = _TIPO_MAP.get(tipo_raw)
            if not operation_type:
                result.errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "validation",
                        "message": f"Unknown tipo: {row.get('tipo')!r} (expected dividendo/jcp/rendimento)",
                    }
                )
                continue

            ticker = row.get("ticker", "").upper()
            operation_date = row.get("data_pagamento", "")
            qty = _parse_number(row.get("quantidade", ""))
            total = _parse_number(row.get("valor_total", ""))

            if not ticker or not operation_date or qty is None or total is None:
                result.errors.append(
                    {
                        "row_index": row_index,
                        "error_type": "validation",
                        "message": (
                            f"Missing required fields "
                            f"(ticker={ticker!r}, data_pagamento={operation_date!r}, "
                            f"quantidade={row.get('quantidade')!r}, valor_total={row.get('valor_total')!r})"
                        ),
                    }
                )
                continue

            gross_cents = _to_cents(total)
            if operation_type == "jcp":
                # Estimate IR retained at source. Real value is typically
                # 14.8%–15.2% per the B3 Movimentação data; 15% is a safe
                # central estimate for historical backfill purposes.
                ir_cents = int(round(gross_cents * _JCP_IR_RATE))
            else:
                ir_cents = 0

            unit_price_reais = (total / qty) if qty > 0 else 0.0
            ir_reais = ir_cents / 100.0

            external_id = (
                f"manual_div:{operation_date}:{operation_type}:{ticker}:{gross_cents}"
            )

            record: dict[str, Any] = {
                "source": self.source_type,
                "external_id": external_id,
                "asset_code": ticker,
                "operation_type": operation_type,
                "operation_date": operation_date,
                "quantity": qty,
                # Monetary fields are passed in BRL (reais) — the normalizer
                # (parse_monetary_cents) is responsible for converting to cents.
                "unit_price": unit_price_reais,
                "gross_value": total,
                "fees": ir_reais,  # estimated IR for JCP, 0 for others
                "notes": (
                    f"manual_dividends_csv:{row.get('tipo')}"
                    + (" (IR estimado 15%)" if operation_type == "jcp" else "")
                ),
                "file_name": file_path.name,
            }
            result.records.append(record)

        return result


__all__ = ["ManualDividendsCsvExtractor"]
