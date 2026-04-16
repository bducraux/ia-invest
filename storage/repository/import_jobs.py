"""Import job repository — audit trail for file imports."""

from __future__ import annotations

import sqlite3
from typing import Any

from domain.models import ImportJob


class ImportJobRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, job: ImportJob) -> int:
        """Insert a new import job and return its generated id."""
        cursor = self._conn.execute(
            """
            INSERT INTO import_jobs (
                portfolio_id, source_type, file_name, file_hash, file_path,
                status, started_at
            ) VALUES (
                :portfolio_id, :source_type, :file_name, :file_hash, :file_path,
                :status, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
            """,
            {
                "portfolio_id": job.portfolio_id,
                "source_type": job.source_type,
                "file_name": job.file_name,
                "file_hash": job.file_hash,
                "file_path": job.file_path,
                "status": job.status,
            },
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def update_status(
        self,
        job_id: int,
        *,
        status: str,
        total_records: int = 0,
        valid_records: int = 0,
        skipped_records: int = 0,
        error_records: int = 0,
    ) -> None:
        self._conn.execute(
            """
            UPDATE import_jobs SET
                status          = :status,
                total_records   = :total_records,
                valid_records   = :valid_records,
                skipped_records = :skipped_records,
                error_records   = :error_records,
                finished_at     = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = :id
            """,
            {
                "id": job_id,
                "status": status,
                "total_records": total_records,
                "valid_records": valid_records,
                "skipped_records": skipped_records,
                "error_records": error_records,
            },
        )
        self._conn.commit()

    def log_error(
        self,
        job_id: int,
        *,
        error_type: str,
        message: str,
        row_index: int | None = None,
        field: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        import json

        self._conn.execute(
            """
            INSERT INTO import_errors (
                import_job_id, row_index, field, error_type, message, raw_data_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                row_index,
                field,
                error_type,
                message,
                json.dumps(raw_data) if raw_data else None,
            ),
        )
        self._conn.commit()

    def get(self, job_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM import_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_by_portfolio(self, portfolio_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM import_jobs
            WHERE portfolio_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (portfolio_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
