"""Tests for the ``get_irpf_report`` MCP tool."""

from __future__ import annotations

from domain.models import Operation, Portfolio
from mcp_server.tools.irpf_report import get_irpf_report
from storage.repository.asset_metadata import AssetMetadata, AssetMetadataRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository


def _seed(db: Database) -> str:
    pid = "default__rv"
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=pid, name="RV", base_currency="BRL", owner_id="default")
    )
    AssetMetadataRepository(db.connection).upsert(
        AssetMetadata(
            asset_code="ITSA4",
            cnpj="61.532.644/0001-15",
            asset_class="acao",
            asset_name_oficial="ITAUSA S.A.",
            source="manual",
        )
    )
    OperationRepository(db.connection).insert_many(
        [
            Operation(
                portfolio_id=pid,
                source="t",
                external_id="b1",
                asset_code="ITSA4",
                asset_type="stock",
                operation_type="buy",
                operation_date="2024-04-10",
                quantity=100,
                unit_price=800,
                gross_value=80000,
            ),
            Operation(
                portfolio_id=pid,
                source="t",
                external_id="d1",
                asset_code="ITSA4",
                asset_type="stock",
                operation_type="dividend",
                operation_date="2024-09-01",
                quantity=0,
                unit_price=0,
                gross_value=15000,
            ),
        ]
    )
    return pid


def test_returns_error_for_unknown_portfolio(tmp_db: Database) -> None:
    result = get_irpf_report(tmp_db, "ghost", base_year=2024)
    assert "error" in result


def test_rejects_invalid_year(tmp_db: Database) -> None:
    pid = _seed(tmp_db)
    assert "error" in get_irpf_report(tmp_db, pid, base_year=1900)
    assert "error" in get_irpf_report(tmp_db, pid, base_year=2200)


def test_payload_shape_and_section_codes(tmp_db: Database) -> None:
    pid = _seed(tmp_db)
    result = get_irpf_report(tmp_db, pid, base_year=2024)

    assert result["portfolio_id"] == pid
    assert result["base_year"] == 2024
    assert "generated_at" in result
    assert isinstance(result["sections"], list)

    sections_by_code = {s["code"]: s for s in result["sections"]}
    assert "09" in sections_by_code
    assert "03-01" in sections_by_code

    # Cód. 09 — dividendo de ITSA4.
    sec_09 = sections_by_code["09"]
    assert sec_09["category"] == "isento"
    assert sec_09["total_cents"] == 15000
    row = sec_09["rows"][0]
    assert row["asset_code"] == "ITSA4"
    assert row["cnpj"] == "61.532.644/0001-15"
    assert row["value_cents"] == 15000
    assert row["extra"] is None  # apenas Bens e Direitos preenchem extra.

    # Cód. 03-01 — Ações com discriminação pronta.
    sec_b = sections_by_code["03-01"]
    assert sec_b["category"] == "bem_direito"
    row_b = sec_b["rows"][0]
    assert row_b["extra"] is not None
    assert row_b["extra"]["quantity"] == 100
    assert row_b["extra"]["total_cents"] == 80000
    assert row_b["discriminacao"]
    assert "ITSA4" in row_b["discriminacao"]
