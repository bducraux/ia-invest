"""MCP tool: ``get_irpf_report`` — DIRPF projection for a renda-variavel portfolio."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from domain.irpf.builder import IrpfReportBuilder
from domain.irpf.classifier import SECTION_CATEGORIES
from storage.repository.asset_metadata import AssetMetadataRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository

_MIN_YEAR = 2000
_MAX_YEAR = 2100


def get_irpf_report(
    db: Database,
    portfolio_id: str,
    *,
    base_year: int,
) -> dict[str, Any]:
    """Build the IRPF report for a portfolio and a given calendar year.

    Returns a snake_case dict suitable for direct JSON serialization.
    Errors (unknown portfolio, invalid year) are returned as ``{"error": ...}``
    so the HTTP layer can map them to ``400``.
    """
    if not isinstance(base_year, int):
        return {"error": "base_year must be an integer"}
    if base_year < _MIN_YEAR or base_year > _MAX_YEAR:
        return {
            "error": (
                f"base_year out of range ({_MIN_YEAR}..{_MAX_YEAR}); got {base_year}"
            )
        }

    portfolio = PortfolioRepository(db.connection).get(portfolio_id)
    if portfolio is None:
        return {"error": f"Portfolio '{portfolio_id}' not found."}

    builder = IrpfReportBuilder(
        OperationRepository(db.connection),
        AssetMetadataRepository(db.connection),
    )
    report = builder.build(portfolio_id, base_year)

    sections_payload: list[dict[str, Any]] = []
    for section in report.sections:
        rows_payload: list[dict[str, Any]] = []
        for row in section.rows:
            row_dict: dict[str, Any] = {
                "asset_code": row.asset_code,
                "asset_name": row.asset_name,
                "cnpj": row.cnpj,
                "value_cents": row.value_cents,
                "warnings": list(row.warnings),
                "discriminacao": row.discriminacao,
                "extra": asdict(row.extra) if row.extra is not None else None,
            }
            rows_payload.append(row_dict)
        sections_payload.append(
            {
                "code": section.code,
                "title": section.title,
                "category": SECTION_CATEGORIES.get(section.code, section.category),
                "total_cents": section.total_cents,
                "rows": rows_payload,
            }
        )

    return {
        "portfolio_id": report.portfolio_id,
        "base_year": report.base_year,
        "generated_at": report.generated_at.isoformat(),
        "warnings": list(report.warnings),
        "sections": sections_payload,
    }
