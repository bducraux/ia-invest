from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Operation, Portfolio, Position
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


def _seed_db(db_path: Path) -> None:
    db = Database(db_path)
    db.initialize()

    portfolio_repo = PortfolioRepository(db.connection)
    operation_repo = OperationRepository(db.connection)
    position_repo = PositionRepository(db.connection)

    portfolio_repo.upsert(
        Portfolio(
            id="carteira-teste",
            name="Carteira Teste",
            base_currency="BRL",
            status="active",
        )
    )

    operation_repo.insert_many(
        [
            Operation(
                portfolio_id="carteira-teste",
                source="broker_csv",
                external_id="op-1",
                asset_code="BBAS3",
                asset_type="stock",
                operation_type="buy",
                operation_date="2026-01-10",
                quantity=10,
                unit_price=2000,
                gross_value=20000,
                fees=0,
            ),
            Operation(
                portfolio_id="carteira-teste",
                source="broker_csv",
                external_id="op-2",
                asset_code="BBAS3",
                asset_type="stock",
                operation_type="dividend",
                operation_date="2026-01-15",
                quantity=10,
                unit_price=50,
                gross_value=500,
                fees=0,
            ),
        ]
    )

    position_repo.upsert(
        Position(
            portfolio_id="carteira-teste",
            asset_code="BBAS3",
            asset_type="stock",
            asset_name="Banco do Brasil",
            quantity=10,
            avg_price=2000,
            total_cost=20000,
            realized_pnl=0,
            dividends=500,
            first_operation_date="2026-01-10",
            last_operation_date="2026-01-15",
        )
    )
    db.close()


def test_list_portfolios_endpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get("/api/portfolios")
    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "carteira-teste",
            "name": "Carteira Teste",
            "currency": "BRL",
        }
    ]


def test_operations_endpoint_maps_types(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get("/api/portfolios/carteira-teste/operations")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 2
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert {op["type"] for op in payload["operations"]} == {"COMPRA", "DIVIDENDO"}


def test_positions_endpoint_contains_frontend_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get("/api/portfolios/carteira-teste/positions")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["positions"]) == 1
    pos = payload["positions"][0]

    assert pos["assetCode"] == "BBAS3"
    assert pos["name"] == "Banco do Brasil"
    assert pos["assetClass"] == "ACAO"
    assert pos["avgPrice"] == 2000
    assert pos["marketPrice"] == 2000
    assert pos["marketValue"] == 20000
    assert pos["unrealizedPnl"] == 0
