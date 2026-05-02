from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Operation, Portfolio
from mcp_server.http_api import create_http_app
from storage.repository.asset_metadata import AssetMetadata, AssetMetadataRepository
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository


def _seed(db_path: Path, *, allowed_asset_types: list[str]) -> str:
    db = Database(db_path)
    db.initialize()
    pid = "default__rv"
    PortfolioRepository(db.connection).upsert(
        Portfolio(
            id=pid,
            name="RV",
            base_currency="BRL",
            owner_id="default",
            config={"rules": {"allowed_asset_types": allowed_asset_types}},
        )
    )
    AssetMetadataRepository(db.connection).upsert(
        AssetMetadata(
            asset_code="ITSA4",
            cnpj="61.532.644/0001-15",
            asset_class_irpf="acao",
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
    db.close()
    return pid


def test_irpf_endpoint_happy_path(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    pid = _seed(db_path, allowed_asset_types=["stock", "fii"])
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get(f"/api/portfolios/{pid}/irpf", params={"year": 2024})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["base_year"] == 2024
    codes = {s["code"] for s in payload["sections"]}
    assert "09" in codes
    assert "03-01" in codes


def test_irpf_endpoint_rejects_non_renda_variavel(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    pid = _seed(db_path, allowed_asset_types=["CDB", "LCI"])
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get(f"/api/portfolios/{pid}/irpf", params={"year": 2024})
    assert response.status_code == 400
    assert "renda-variavel" in response.json()["detail"].lower()


def test_irpf_endpoint_404_for_unknown_portfolio(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed(db_path, allowed_asset_types=["stock"])
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get("/api/portfolios/ghost/irpf", params={"year": 2024})
    assert response.status_code == 404


def test_irpf_endpoint_validates_year_range(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    pid = _seed(db_path, allowed_asset_types=["stock"])
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get(f"/api/portfolios/{pid}/irpf", params={"year": 1900})
    assert response.status_code == 422
