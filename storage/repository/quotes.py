"""Quote cache repository for market prices in cents."""

from __future__ import annotations

import sqlite3
from typing import Any


class QuoteRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_quotes_cache (
                asset_code  TEXT PRIMARY KEY,
                price_cents INTEGER NOT NULL,
                source      TEXT NOT NULL,
                fetched_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_quotes_fetched_at
            ON market_quotes_cache(fetched_at)
            """
        )
        self._conn.commit()

    def get_fresh(self, asset_code: str, *, max_age_seconds: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                asset_code,
                price_cents,
                source,
                fetched_at,
                (CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', fetched_at) AS INTEGER))
                    AS age_seconds
            FROM market_quotes_cache
            WHERE asset_code = ?
            """,
            (asset_code.upper(),),
        ).fetchone()
        if row is None:
            return None

        age_seconds = int(row["age_seconds"]) if row["age_seconds"] is not None else max_age_seconds + 1
        if age_seconds > max_age_seconds:
            return None
        return dict(row)

    def get_latest(self, asset_code: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                asset_code,
                price_cents,
                source,
                fetched_at,
                (CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', fetched_at) AS INTEGER))
                    AS age_seconds
            FROM market_quotes_cache
            WHERE asset_code = ?
            """,
            (asset_code.upper(),),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def upsert(self, asset_code: str, price_cents: int, source: str) -> None:
        self._conn.execute(
            """
            INSERT INTO market_quotes_cache (asset_code, price_cents, source, fetched_at)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(asset_code) DO UPDATE SET
                price_cents = excluded.price_cents,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            (asset_code.upper(), price_cents, source),
        )
        self._conn.commit()
