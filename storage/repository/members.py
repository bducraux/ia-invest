"""Member repository — CRUD for the `members` table."""

from __future__ import annotations

import sqlite3

from domain.members import Member


class MemberRepository:
    """Data access layer for members of the family/owners of portfolios."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------ writes
    def upsert(self, member: Member) -> None:
        """Insert or update a member record (idempotent)."""
        self._conn.execute(
            """
            INSERT INTO members (id, name, display_name, email, status, updated_at)
            VALUES (:id, :name, :display_name, :email, :status,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(id) DO UPDATE SET
                name         = excluded.name,
                display_name = excluded.display_name,
                email        = excluded.email,
                status       = excluded.status,
                updated_at   = excluded.updated_at
            """,
            {
                "id": member.id,
                "name": member.name,
                "display_name": member.display_name,
                "email": member.email,
                "status": member.status,
            },
        )
        self._conn.commit()

    def set_status(self, member_id: str, status: str) -> None:
        self._conn.execute(
            """
            UPDATE members
               SET status     = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
             WHERE id = ?
            """,
            (status, member_id),
        )
        self._conn.commit()

    def delete(self, member_id: str) -> None:
        """Hard-delete a member.

        Raises ValueError if the member still owns one or more portfolios —
        callers should use `MemberService.inactivate` instead.
        """
        if self.count_portfolios(member_id) > 0:
            raise ValueError(
                f"Cannot delete member '{member_id}': still owns one or more "
                "portfolios. Inactivate or transfer ownership first."
            )
        self._conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        self._conn.commit()

    # ------------------------------------------------------------------- reads
    def get(self, member_id: str) -> Member | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE id = ?", (member_id,)
        ).fetchone()
        return self._row_to_member(row) if row else None

    def get_by_email(self, email: str) -> Member | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE email = ?", (email,)
        ).fetchone()
        return self._row_to_member(row) if row else None

    def get_by_id_or_name(self, value: str) -> Member | None:
        """Resolve a member by id (exact) or by name (case-insensitive)."""
        row = self._conn.execute(
            """
            SELECT * FROM members
             WHERE id = :v
                OR LOWER(name) = LOWER(:v)
                OR LOWER(COALESCE(display_name, '')) = LOWER(:v)
             LIMIT 1
            """,
            {"v": value},
        ).fetchone()
        return self._row_to_member(row) if row else None

    def list_active(self) -> list[Member]:
        rows = self._conn.execute(
            "SELECT * FROM members WHERE status = 'active' ORDER BY id"
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def list_all(self) -> list[Member]:
        rows = self._conn.execute(
            "SELECT * FROM members ORDER BY id"
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def count_portfolios(self, member_id: str, *, only_active: bool = False) -> int:
        """Return the number of portfolios owned by this member."""
        query = "SELECT COUNT(*) AS n FROM portfolios WHERE owner_id = ?"
        params: tuple[object, ...] = (member_id,)
        if only_active:
            query += " AND status = 'active'"
        row = self._conn.execute(query, params).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------- utils
    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> Member:
        return Member(
            id=row["id"],
            name=row["name"],
            display_name=row["display_name"],
            email=row["email"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
