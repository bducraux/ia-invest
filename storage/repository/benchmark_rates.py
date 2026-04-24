"""Repository for the historical ``daily_benchmark_rates`` cache.

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
    # Validate by parsing; raises ValueError if malformed.
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _from_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


class BenchmarkRatesRepository:
    """Read/write helper for the ``daily_benchmark_rates`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert_many(
        self,
        benchmark: str,
        rows: Iterable[tuple[date | str, Decimal | str]],
        *,
        commit: bool = True,
    ) -> int:
        """Insert/replace many ``(date, rate)`` rows in a single transaction.

        Returns the number of rows persisted. Rate may be a :class:`Decimal`
        or a string that can be parsed by ``Decimal(str(value))``.
        """
        bench = benchmark.upper()
        payload: list[tuple[str, str, str]] = []
        for raw_date, raw_rate in rows:
            iso = _to_iso(raw_date)
            # Force string roundtrip to guarantee precision is preserved.
            rate_str = str(Decimal(str(raw_rate)))
            payload.append((bench, iso, rate_str))

        if not payload:
            return 0

        self._conn.executemany(
            """
            INSERT INTO daily_benchmark_rates (benchmark, rate_date, rate, fetched_at)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(benchmark, rate_date) DO UPDATE SET
                rate = excluded.rate,
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

    def get_range(
        self,
        benchmark: str,
        start_date: date | str,
        end_date: date | str,
    ) -> dict[date, Decimal]:
        """Return all stored rates within the inclusive range."""
        bench = benchmark.upper()
        start = _to_iso(start_date)
        end = _to_iso(end_date)
        cursor = self._conn.execute(
            """
            SELECT rate_date, rate
            FROM daily_benchmark_rates
            WHERE benchmark = ? AND rate_date >= ? AND rate_date <= ?
            ORDER BY rate_date ASC
            """,
            (bench, start, end),
        )
        return {_from_iso(row["rate_date"]): Decimal(row["rate"]) for row in cursor.fetchall()}

    def get_coverage(self, benchmark: str) -> tuple[date | None, date | None, int]:
        """Return ``(min_date, max_date, row_count)`` for a benchmark.

        Both dates are ``None`` when no rows exist; ``row_count`` is always
        an int (zero when empty).
        """
        bench = benchmark.upper()
        row = self._conn.execute(
            """
            SELECT
                MIN(rate_date) AS min_date,
                MAX(rate_date) AS max_date,
                COUNT(*)       AS n
            FROM daily_benchmark_rates
            WHERE benchmark = ?
            """,
            (bench,),
        ).fetchone()
        if row is None or row["n"] == 0:
            return None, None, 0
        return _from_iso(row["min_date"]), _from_iso(row["max_date"]), int(row["n"])

    def get_last_fetched_at(self, benchmark: str) -> str | None:
        bench = benchmark.upper()
        row = self._conn.execute(
            """
            SELECT MAX(fetched_at) AS last_fetched_at
            FROM daily_benchmark_rates
            WHERE benchmark = ?
            """,
            (bench,),
        ).fetchone()
        if row is None:
            return None
        return row["last_fetched_at"]
