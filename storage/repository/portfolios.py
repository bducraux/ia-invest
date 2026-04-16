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
            INSERT INTO portfolios (id, name, description, base_currency, status, config_json,
                                    updated_at)
            VALUES (:id, :name, :description, :base_currency, :status, :config_json,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(id) DO UPDATE SET
                name          = excluded.name,
                description   = excluded.description,
                base_currency = excluded.base_currency,
                status        = excluded.status,
                config_json   = excluded.config_json,
                updated_at    = excluded.updated_at
            """,
            {
                "id": portfolio.id,
                "name": portfolio.name,
                "description": portfolio.description,
                "base_currency": portfolio.base_currency,
                "status": portfolio.status,
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

    @staticmethod
    def _row_to_portfolio(row: sqlite3.Row) -> Portfolio:
        config: dict[str, Any] | None = (
            json.loads(row["config_json"]) if row["config_json"] else None
        )
        return Portfolio(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            base_currency=row["base_currency"],
            status=row["status"],
            config=config,
        )
