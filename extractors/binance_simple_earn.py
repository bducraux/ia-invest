"""Binance Simple Earn extractor — parses Binance Simple Earn (Flexible) history
CSV exports.

Expected headers (Portuguese): Tempo, Moeda, Quantidade, Tipo

Date formats:
- ``yy-mm-dd HH:MM:SS``  (e.g., ``26-04-15 00:29:21``)
- ``YYYY-MM-DD``          (e.g., ``2026-04-14``)

Event types handled (all mapped to ``split_bonus`` / zero-cost):
- Real-time APR Rewards
- Bonus Tiered APR Rewards
- Rewards

Domain rule: earned crypto enters with zero cost, which reduces the average
price of the position automatically (cost stays the same, quantity increases).
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from extractors.base import BaseExtractor, ExtractionResult

# All known Simple Earn event types → zero-cost reward
_REWARD_TYPES = {
    "real-time apr rewards",
    "bonus tiered apr rewards",
    "rewards",
}

_SOURCE_TYPE = "binance_simple_earn"


def _normalize_date(raw: str) -> str:
    """Normalize date string to YYYY-MM-DD.

    Supports:
    - ``YYYY-MM-DD``           (already normalized)
    - ``yy-mm-dd HH:MM:SS``   (2-digit year with time)
    """
    raw = raw.strip()
    # Try full ISO first
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # 2-digit year formats
    for fmt in ("%y-%m-%d %H:%M:%S", "%y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Unrecognised date format: {raw!r}")


def _generate_external_id(raw_date: str, asset: str, qty: str, tipo: str) -> str:
    """Use the raw (pre-normalization) timestamp so that two rewards of the
    same size on the same day but different times get distinct IDs."""
    key = f"{raw_date.strip()}|{asset}|{tipo}|{qty}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class BinanceSimpleEarnExtractor(BaseExtractor):
    """Extractor for Binance Simple Earn (Flexible) CSV history files."""

    @property
    def source_type(self) -> str:
        return _SOURCE_TYPE

    def can_handle(self, file_path: Path) -> bool:
        """Return True when the file contains Binance Simple Earn headers."""
        try:
            with file_path.open(encoding="utf-8-sig") as fh:
                first_line = fh.readline().strip()
            # Require all four expected column names
            return all(
                col in first_line for col in ("Tempo", "Moeda", "Quantidade", "Tipo")
            ) and "Par" not in first_line  # exclude binance_csv (has Par / Pair)
        except Exception:
            return False

    def extract(self, file_path: Path) -> ExtractionResult:
        result = ExtractionResult(source_type=_SOURCE_TYPE)

        try:
            raw = file_path.read_bytes().decode("utf-8-sig")
        except Exception as exc:
            result.errors.append({"file": str(file_path), "error": str(exc)})
            return result

        reader = csv.DictReader(io.StringIO(raw))

        for row_num, row in enumerate(reader, start=2):
            try:
                record = self._map_row(row, file_path)
                if record is None:
                    continue
                result.records.append(record)
            except Exception as exc:
                result.errors.append(
                    {
                        "file": str(file_path),
                        "row": row_num,
                        "error": str(exc),
                        "raw": dict(row),
                    }
                )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _map_row(self, row: dict[str, str], file_path: Path) -> dict[str, Any] | None:
        raw_date = row.get("Tempo", "").strip()
        asset = row.get("Moeda", "").strip().upper()
        raw_qty = row.get("Quantidade", "").strip()
        tipo = row.get("Tipo", "").strip()

        if not raw_date or not asset or not raw_qty:
            return None

        # Skip zero-quantity rows (historical records with no actual reward)
        try:
            qty_float = float(raw_qty)
        except ValueError:
            return None
        if qty_float == 0:
            return None

        # Only handle known reward event types
        if tipo.lower() not in _REWARD_TYPES:
            return None

        date_str = _normalize_date(raw_date)
        external_id = _generate_external_id(raw_date, asset, raw_qty, tipo)

        return {
            "source": _SOURCE_TYPE,
            "external_id": external_id,
            "asset_code": asset,
            "asset_type": "crypto",
            "operation_type": "split_bonus",
            "operation_date": date_str,
            "quantity": raw_qty,
            "unit_price": "0",
            "gross_value": "0",
            "fees": "0",
            "broker": "binance",
            "file_name": file_path.name,
            "raw_data": dict(row),
        }
