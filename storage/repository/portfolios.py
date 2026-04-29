"""Portfolio repository — CRUD operations for the portfolios table."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from domain.models import Portfolio


class PortfolioRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, portfolio: Portfolio) -> None:
        """Insert or replace a portfolio record (idempotent)."""
        config_json = json.dumps(portfolio.config) if portfolio.config else None
        self._conn.execute(
            """
            INSERT INTO portfolios (id, name, description, base_currency, status,
                                    owner_id, config_json, updated_at)
            VALUES (:id, :name, :description, :base_currency, :status,
                    :owner_id, :config_json,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(id) DO UPDATE SET
                name          = excluded.name,
                description   = excluded.description,
                base_currency = excluded.base_currency,
                status        = excluded.status,
                owner_id      = excluded.owner_id,
                config_json   = excluded.config_json,
                updated_at    = excluded.updated_at
            """,
            {
                "id": portfolio.id,
                "name": portfolio.name,
                "description": portfolio.description,
                "base_currency": portfolio.base_currency,
                "status": portfolio.status,
                "owner_id": portfolio.owner_id,
                "config_json": config_json,
            },
        )
        self._conn.commit()

    def get(self, portfolio_id: str) -> Portfolio | None:
        row = self._conn.execute(
            "SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        return self._row_to_portfolio(row) if row else None

    def list_active(self) -> list[Portfolio]:
        rows = self._conn.execute(
            "SELECT * FROM portfolios WHERE status = 'active' ORDER BY id"
        ).fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    def list_all(self) -> list[Portfolio]:
        rows = self._conn.execute(
            "SELECT * FROM portfolios ORDER BY id"
        ).fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    def list_by_owner(
        self, owner_id: str, *, only_active: bool = True
    ) -> list[Portfolio]:
        """Return portfolios belonging to a specific member."""
        query = "SELECT * FROM portfolios WHERE owner_id = ?"
        params: tuple[object, ...] = (owner_id,)
        if only_active:
            query += " AND status = 'active'"
        query += " ORDER BY id"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    def transfer_ownership(self, portfolio_id: str, new_owner_id: str) -> None:
        """Reassign a portfolio to a different member.

        Raises ValueError if the portfolio does not exist or the target member
        is missing.  FK enforcement at the SQLite layer also catches missing
        members but the explicit check provides a friendlier error message.
        """
        existing = self.get(portfolio_id)
        if existing is None:
            raise ValueError(f"Portfolio '{portfolio_id}' not found")

        target = self._conn.execute(
            "SELECT id FROM members WHERE id = ?", (new_owner_id,)
        ).fetchone()
        if target is None:
            raise ValueError(f"Member '{new_owner_id}' not found")

        self._conn.execute(
            """
            UPDATE portfolios
               SET owner_id   = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
             WHERE id = ?
            """,
            (new_owner_id, portfolio_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_portfolio(row: sqlite3.Row) -> Portfolio:
        config: dict[str, Any] | None = (
            json.loads(row["config_json"]) if row["config_json"] else None
        )
        # Defensive: legacy databases may have rows without owner_id; the
        # canonical schema enforces NOT NULL so this only matters for tests
        # that interact with hand-rolled fixtures.
        try:
            owner_id = row["owner_id"] or "default"
        except IndexError:
            owner_id = "default"
        return Portfolio(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            base_currency=row["base_currency"],
            status=row["status"],
            owner_id=owner_id,
            config=config,
        )
