"""Repository for the ``avenue_symbol_aliases`` cache.

Stores a per-portfolio mapping ``asset_name → asset_code (ticker)`` learned
incrementally from imported Avenue/Apex monthly PDF statements.

Names are normalized (uppercased, collapsed whitespace) before storage so
lookups are robust to formatting differences across statements.
"""

from __future__ import annotations

import re
import sqlite3

_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Return the canonical form of an asset description used as cache key."""
    return _WS_RE.sub(" ", (name or "").strip().upper())


class AvenueAliasesRepository:
    """Read/write helper for the ``avenue_symbol_aliases`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, portfolio_id: str, asset_name: str) -> tuple[str, str | None] | None:
        """Return ``(asset_code, cusip)`` for the normalized name or ``None``."""
        key = normalize_name(asset_name)
        if not key:
            return None
        row = self._conn.execute(
            "SELECT asset_code, cusip FROM avenue_symbol_aliases "
            "WHERE portfolio_id = ? AND asset_name = ?",
            (portfolio_id, key),
        ).fetchone()
        if row is None:
            return None
        return (row[0], row[1])

    def upsert(
        self,
        portfolio_id: str,
        asset_name: str,
        asset_code: str,
        cusip: str | None = None,
        *,
        commit: bool = True,
    ) -> None:
        """Insert or update an alias. Existing CUSIP is preserved when not provided."""
        key = normalize_name(asset_name)
        code = (asset_code or "").strip().upper()
        if not key or not code:
            return
        cusip_clean = (cusip or "").strip() or None
        self._conn.execute(
            """
            INSERT INTO avenue_symbol_aliases
                (portfolio_id, asset_name, asset_code, cusip)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(portfolio_id, asset_name) DO UPDATE SET
                asset_code = excluded.asset_code,
                cusip = COALESCE(excluded.cusip, avenue_symbol_aliases.cusip),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (portfolio_id, key, code, cusip_clean),
        )
        if commit:
            self._conn.commit()

    def list_all(self, portfolio_id: str) -> dict[str, tuple[str, str | None]]:
        """Return ``{normalized_name: (asset_code, cusip)}`` for the portfolio."""
        rows = self._conn.execute(
            "SELECT asset_name, asset_code, cusip FROM avenue_symbol_aliases "
            "WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchall()
        return {row[0]: (row[1], row[2]) for row in rows}
