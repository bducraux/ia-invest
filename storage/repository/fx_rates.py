"""Repository for the historical ``fx_rates`` cache.

Rates are stored as TEXT and round-tripped through :class:`~decimal.Decimal`
so we never lose precision to float conversion.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal


def _to_iso(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _from_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


class FxRatesRepository:
    """Read/write helper for the ``fx_rates`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert_many(
        self,
        pair: str,
        rows: Iterable[tuple[date | str, Decimal | str]],
        *,
        source: str,
        commit: bool = True,
    ) -> int:
        """Insert/replace many ``(date, rate)`` rows for a single pair."""
        pair_u = pair.upper()
        payload: list[tuple[str, str, str, str]] = []
        for raw_date, raw_rate in rows:
            iso = _to_iso(raw_date)
            rate_str = str(Decimal(str(raw_rate)))
            payload.append((pair_u, iso, rate_str, source))

        if not payload:
            return 0

        self._conn.executemany(
            """
            INSERT INTO fx_rates (pair, rate_date, rate, source, fetched_at)
            VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(pair, rate_date) DO UPDATE SET
                rate = excluded.rate,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            payload,
        )
        if commit:
            self._conn.commit()
        return len(payload)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_rate(self, pair: str, rate_date: date | str) -> tuple[Decimal, str] | None:
        """Return ``(rate, source)`` for the exact date or ``None``."""
        row = self._conn.execute(
            """
            SELECT rate, source FROM fx_rates
            WHERE pair = ? AND rate_date = ?
            """,
            (pair.upper(), _to_iso(rate_date)),
        ).fetchone()
        if row is None:
            return None
        return Decimal(row["rate"]), str(row["source"])

    def get_latest_on_or_before(
        self, pair: str, rate_date: date | str
    ) -> tuple[date, Decimal, str] | None:
        """Return the most recent ``(date, rate, source)`` at or before ``rate_date``."""
        row = self._conn.execute(
            """
            SELECT rate_date, rate, source FROM fx_rates
            WHERE pair = ? AND rate_date <= ?
            ORDER BY rate_date DESC
            LIMIT 1
            """,
            (pair.upper(), _to_iso(rate_date)),
        ).fetchone()
        if row is None:
            return None
        return _from_iso(row["rate_date"]), Decimal(row["rate"]), str(row["source"])

    def get_coverage(self, pair: str) -> tuple[date | None, date | None, int]:
        row = self._conn.execute(
            """
            SELECT MIN(rate_date) AS min_date,
                   MAX(rate_date) AS max_date,
                   COUNT(*)       AS n
            FROM fx_rates
            WHERE pair = ?
            """,
            (pair.upper(),),
        ).fetchone()
        if row is None or row["n"] == 0:
            return None, None, 0
        return _from_iso(row["min_date"]), _from_iso(row["max_date"]), int(row["n"])

    def get_last_fetched_at(self, pair: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT MAX(fetched_at) AS last_fetched_at
            FROM fx_rates
            WHERE pair = ?
            """,
            (pair.upper(),),
        ).fetchone()
        if row is None:
            return None
        return row["last_fetched_at"]
