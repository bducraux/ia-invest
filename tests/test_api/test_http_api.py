from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Operation, Portfolio, Position
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository
from storage.repository.quotes import QuoteRepository


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
            config={"rules": {"allowed_asset_types": ["stock", "fii"]}},
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
            "allowedAssetTypes": ["stock", "fii"],
            "specialization": "RENDA_VARIAVEL",
            "ownerId": "default",
            "owner": {
                "id": "default",
                "name": "Default Member",
                "displayName": None,
                "email": None,
                "status": "active",
            },
        }
    ]


def test_list_portfolios_endpoint_exposes_specialization_for_fixed_income(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    db = Database(db_path)
    db.initialize()

    PortfolioRepository(db.connection).upsert(
        Portfolio(
            id="renda-fixa-bruno",
            name="Renda Fixa Bruno",
            base_currency="BRL",
            status="active",
            config={"rules": {"allowed_asset_types": ["CDB", "LCI", "LCA"]}},
        )
    )
    db.close()

    client = TestClient(create_http_app(db_path, quotes_enabled=False))
    response = client.get("/api/portfolios")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "renda-fixa-bruno",
            "name": "Renda Fixa Bruno",
            "currency": "BRL",
            "allowedAssetTypes": ["CDB", "LCI", "LCA"],
            "specialization": "RENDA_FIXA",
            "ownerId": "default",
            "owner": {
                "id": "default",
                "name": "Default Member",
                "displayName": None,
                "email": None,
                "status": "active",
            },
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


def test_operations_endpoint_filters_by_asset_class(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.get("/api/portfolios/carteira-teste/operations?assetClass=RENDA_VARIAVEL")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 2
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
    assert pos["quoteStatus"] == "avg_fallback"
    assert pos["quoteSource"] == "avg_price"

    filtered = client.get("/api/portfolios/carteira-teste/positions?assetClass=RENDA_VARIAVEL")
    assert filtered.status_code == 200
    assert len(filtered.json()["positions"]) == 1
    assert filtered.json()["positions"][0]["assetClass"] == "ACAO"


def test_positions_endpoint_uses_cached_quote_before_avg_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)

    db = Database(db_path)
    db.initialize()
    quote_repo = QuoteRepository(db.connection)
    quote_repo.upsert("BBAS3", 2450, "test-feed")
    db.close()

    client = TestClient(create_http_app(db_path, quotes_enabled=False))
    response = client.get("/api/portfolios/carteira-teste/positions")
    assert response.status_code == 200
    payload = response.json()

    pos = payload["positions"][0]
    assert pos["marketPrice"] == 2450
    assert pos["quoteStatus"] in {"cache_fresh", "cache_stale"}
    assert pos["quoteSource"] == "test-feed"


def test_refresh_quotes_endpoint_returns_status_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    _seed_db(db_path)

    db = Database(db_path)
    db.initialize()
    position_repo = PositionRepository(db.connection)
    quote_repo = QuoteRepository(db.connection)

    position_repo.upsert(
        Position(
            portfolio_id="carteira-teste",
            asset_code="ZZZZ9",
            asset_type="stock",
            asset_name="Ativo Sem Cotacao",
            quantity=5,
            avg_price=1000,
            total_cost=5000,
            realized_pnl=0,
            dividends=0,
            first_operation_date="2026-01-10",
            last_operation_date="2026-01-15",
        )
    )
    quote_repo.upsert("ZZZZ9", 1234, "cache-test")
    db.close()

    client = TestClient(create_http_app(db_path, quotes_enabled=True))
    response = client.post("/api/portfolios/carteira-teste/quotes/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "portfolio"
    assert payload["portfolios"] == ["carteira-teste"]
    assert payload["totalAssets"] >= 1
    assert payload["cacheStaleCount"] + payload["liveCount"] + payload["failedCount"] >= 1
