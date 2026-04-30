"""Repository for the persistent ``historical_prices`` cache.

Closing prices are immutable once a date is past, so this cache has no TTL —
entries are written once and reused indefinitely. Currency is stored to
support international assets; conversion to BRL happens elsewhere via
:mod:`storage.repository.fx_rates`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime


def _to_iso(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _from_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


class HistoricalPricesRepository:
    """Read/write helper for the ``historical_prices`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert_many(
        self,
        rows: Iterable[tuple[str, date | str, int, str, str]],
        *,
        commit: bool = True,
    ) -> int:
        """Insert/replace many ``(asset_code, date, close_cents, currency, source)`` rows."""
        payload = [
            (asset_code.upper(), _to_iso(d), int(close_cents), currency.upper(), source)
            for asset_code, d, close_cents, currency, source in rows
        ]
        if not payload:
            return 0
        self._conn.executemany(
            """
            INSERT INTO historical_prices (asset_code, rate_date, close_cents, currency, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(asset_code, rate_date) DO UPDATE SET
                close_cents = excluded.close_cents,
                currency    = excluded.currency,
                source      = excluded.source,
                fetched_at  = excluded.fetched_at
            """,
            payload,
        )
        if commit:
            self._conn.commit()
        return len(payload)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_close_on(
        self, asset_code: str, rate_date: date | str
    ) -> tuple[int, str, str] | None:
        """Return ``(close_cents, currency, source)`` for the exact date or ``None``."""
        row = self._conn.execute(
            """
            SELECT close_cents, currency, source
            FROM historical_prices
            WHERE asset_code = ? AND rate_date = ?
            """,
            (asset_code.upper(), _to_iso(rate_date)),
        ).fetchone()
        if row is None:
            return None
        return int(row["close_cents"]), str(row["currency"]), str(row["source"])

    def get_latest_on_or_before(
        self, asset_code: str, rate_date: date | str
    ) -> tuple[date, int, str, str] | None:
        """Return most recent ``(date, close_cents, currency, source)`` at/before ``rate_date``."""
        row = self._conn.execute(
            """
            SELECT rate_date, close_cents, currency, source
            FROM historical_prices
            WHERE asset_code = ? AND rate_date <= ?
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            (asset_code.upper(), _to_iso(rate_date)),
        ).fetchone()
        if row is None:
            return None
        return (
            _from_iso(row["rate_date"]),
            int(row["close_cents"]),
            str(row["currency"]),
            str(row["source"]),
        )

    def get_coverage(self, asset_code: str) -> tuple[date | None, date | None, int]:
        row = self._conn.execute(
            """
            SELECT MIN(rate_date) AS min_date,
                   MAX(rate_date) AS max_date,
                   COUNT(*)       AS n
            FROM historical_prices
            WHERE asset_code = ?
            """,
            (asset_code.upper(),),
        ).fetchone()
        if row is None or row["n"] == 0:
            return None, None, 0
        return _from_iso(row["min_date"]), _from_iso(row["max_date"]), int(row["n"])

    def list_distinct_assets(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT asset_code FROM historical_prices ORDER BY asset_code"
        ).fetchall()
        return [str(r["asset_code"]) for r in rows]
