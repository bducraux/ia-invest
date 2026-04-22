from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Portfolio
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository
from domain.previdencia import PrevidenciaSnapshot


def _seed_previdencia_db(db_path: Path) -> None:
    db = Database(db_path)
    db.initialize()

    portfolio_repo = PortfolioRepository(db.connection)
    portfolio_repo.upsert(
        Portfolio(
            id="fundacao-ibm",
            name="Fundacao IBM",
            base_currency="BRL",
            status="active",
        )
    )

    prev_repo = PrevidenciaSnapshotRepository(db.connection)
    prev_repo.upsert_if_newer(
        PrevidenciaSnapshot(
            portfolio_id="fundacao-ibm",
            asset_code="PREV_IBM_CD",
            product_name="IBM CD",
            quantity=9104.743,
            unit_price_cents=4751,
            market_value_cents=43260628,
            period_month="2026-03",
            period_start_date="2026-03-01",
            period_end_date="2026-03-31",
            source_file="extrato_março_2026.pdf",
        )
    )
    db.close()


def test_positions_endpoint_includes_previdencia_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_previdencia_db(db_path)

    client = TestClient(create_http_app(db_path, quotes_enabled=False))
    response = client.get("/api/portfolios/fundacao-ibm/positions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["positions"]) == 1
    pos = payload["positions"][0]

    assert pos["assetCode"] == "PREV_IBM_CD"
    assert pos["assetClass"] == "PREVIDENCIA"
    assert pos["quoteSource"] == "previdencia_statement"
    assert pos["marketPrice"] == 4751


def test_summary_endpoint_includes_previdencia_allocation(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_previdencia_db(db_path)

    client = TestClient(create_http_app(db_path, quotes_enabled=False))
    response = client.get("/api/portfolios/fundacao-ibm/summary")

    assert response.status_code == 200
    payload = response.json()

    allocation = {slice_["assetClass"]: slice_ for slice_ in payload["allocation"]}
    assert "PREVIDENCIA" in allocation
    assert allocation["PREVIDENCIA"]["label"] == "Previdencia"
    assert allocation["PREVIDENCIA"]["value"] == 43260628
