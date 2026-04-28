"""Integration tests for close-position and operation CRUD endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Operation, Portfolio
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.operations import OperationRepository
from storage.repository.portfolios import PortfolioRepository
from storage.repository.positions import PositionRepository


PORTFOLIO_ID = "rv-portfolio"


def _seed(db_path: Path) -> Database:
    db = Database(db_path)
    db.initialize()
    PortfolioRepository(db.connection).upsert(
        Portfolio(
            id=PORTFOLIO_ID,
            name="RV",
            base_currency="BRL",
            status="active",
            config={
                "rules": {"allowed_asset_types": ["stock", "fii"]},
                "import": {"move_processed_files": False},
            },
        )
    )
    return db


def _client(tmp_path: Path) -> tuple[TestClient, Database]:
    db_path = tmp_path / "ia.db"
    db = _seed(db_path)
    return TestClient(create_http_app(db_path, quotes_enabled=False)), db


def _insert_buy(
    db: Database,
    asset_code: str,
    quantity: float,
    unit_price: int,
    op_date: str,
    *,
    external_id: str | None = None,
) -> int:
    op = Operation(
        portfolio_id=PORTFOLIO_ID,
        source="manual",
        external_id=external_id or f"{asset_code}-{op_date}-{quantity}-{unit_price}",
        asset_code=asset_code,
        asset_type="stock",
        operation_type="buy",
        operation_date=op_date,
        quantity=quantity,
        unit_price=unit_price,
        gross_value=int(round(quantity * unit_price)),
    )
    OperationRepository(db.connection).insert_many([op])
    row = db.connection.execute(
        "SELECT id FROM operations WHERE portfolio_id = ? AND asset_code = ? "
        "AND operation_date = ? ORDER BY id DESC LIMIT 1",
        (PORTFOLIO_ID, asset_code, op_date),
    ).fetchone()
    return int(row["id"])


def _recompute_via_service(db: Database) -> None:
    from domain.position_service import PositionService

    op_repo = OperationRepository(db.connection)
    pos_repo = PositionRepository(db.connection)
    all_ops = op_repo.list_all_by_portfolio(PORTFOLIO_ID)
    positions = PositionService().calculate(all_ops, PORTFOLIO_ID)
    pos_repo.upsert_many(positions)


def test_close_position_deletes_operations_and_positions_row(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    _insert_buy(db, "PETR4", 100, 3500, "2024-01-15")
    _insert_buy(db, "PETR4", 50, 3700, "2024-02-15")
    _insert_buy(db, "VALE3", 80, 6500, "2024-01-20")
    _recompute_via_service(db)

    resp = client.delete(f"/api/portfolios/{PORTFOLIO_ID}/positions/PETR4")
    assert resp.status_code == 204

    op_repo = OperationRepository(db.connection)
    pos_repo = PositionRepository(db.connection)
    assert op_repo.count_by_asset(PORTFOLIO_ID, "PETR4") == 0
    assert pos_repo.get(PORTFOLIO_ID, "PETR4") is None
    # Other asset remains untouched.
    assert op_repo.count_by_asset(PORTFOLIO_ID, "VALE3") == 1
    assert pos_repo.get(PORTFOLIO_ID, "VALE3") is not None


def test_delete_operation_recomputes_position(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    op1 = _insert_buy(db, "PETR4", 100, 3500, "2024-01-15")
    _insert_buy(db, "PETR4", 50, 3700, "2024-02-15")
    _recompute_via_service(db)

    resp = client.delete(f"/api/portfolios/{PORTFOLIO_ID}/operations/{op1}")
    assert resp.status_code == 204

    pos = PositionRepository(db.connection).get(PORTFOLIO_ID, "PETR4")
    assert pos is not None
    assert pos.quantity == 50.0


def test_delete_last_operation_drops_positions_row(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    op_id = _insert_buy(db, "PETR4", 100, 3500, "2024-01-15")
    _recompute_via_service(db)

    resp = client.delete(f"/api/portfolios/{PORTFOLIO_ID}/operations/{op_id}")
    assert resp.status_code == 204
    assert PositionRepository(db.connection).get(PORTFOLIO_ID, "PETR4") is None


def test_update_operation_recomputes_and_neutralises_external_id(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    op_id = _insert_buy(db, "PETR4", 100, 3500, "2024-01-15", external_id="EXT-1")
    _recompute_via_service(db)

    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/operations/{op_id}",
        json={"quantity": 200, "grossValue": 700_000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quantity"] == 200
    assert body["external_id"] == f"manual:edited:{op_id}"

    pos = PositionRepository(db.connection).get(PORTFOLIO_ID, "PETR4")
    assert pos is not None
    assert pos.quantity == 200.0


def test_update_operation_changes_asset_recomputes_both(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    op_id = _insert_buy(db, "PETR4", 100, 3500, "2024-01-15")
    _recompute_via_service(db)

    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/operations/{op_id}",
        json={"assetCode": "VALE3"},
    )
    assert resp.status_code == 200, resp.text

    pos_repo = PositionRepository(db.connection)
    assert pos_repo.get(PORTFOLIO_ID, "PETR4") is None
    vale = pos_repo.get(PORTFOLIO_ID, "VALE3")
    assert vale is not None
    assert vale.quantity == 100.0


def test_delete_operation_unknown_returns_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.delete(f"/api/portfolios/{PORTFOLIO_ID}/operations/9999")
    assert resp.status_code == 404


def test_update_operation_with_empty_payload_returns_422(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    op_id = _insert_buy(db, "PETR4", 100, 3500, "2024-01-15")
    _recompute_via_service(db)
    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/operations/{op_id}", json={}
    )
    assert resp.status_code == 422


def test_create_operation_inserts_and_recomputes(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    payload = {
        "assetCode": "PETR4",
        "assetType": "stock",
        "operationType": "buy",
        "operationDate": "2024-03-10",
        "quantity": 50,
        "unitPrice": 3000,
        "grossValue": 150000,
    }
    resp = client.post(
        f"/api/portfolios/{PORTFOLIO_ID}/operations", json=payload
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["asset_code"] == "PETR4"
    assert body["external_id"].startswith("manual:created:")
    petr = PositionRepository(db.connection).get(PORTFOLIO_ID, "PETR4")
    assert petr is not None
    assert petr.quantity == 50.0


def test_create_operation_missing_required_returns_422(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    payload = {
        "assetCode": "PETR4",
        # assetType missing
        "operationType": "buy",
        "operationDate": "2024-03-10",
        "quantity": 50,
        "unitPrice": 3000,
        "grossValue": 150000,
    }
    resp = client.post(
        f"/api/portfolios/{PORTFOLIO_ID}/operations", json=payload
    )
    assert resp.status_code == 422


def test_create_operation_unknown_portfolio_returns_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    payload = {
        "assetCode": "PETR4",
        "assetType": "stock",
        "operationType": "buy",
        "operationDate": "2024-03-10",
        "quantity": 50,
        "unitPrice": 3000,
        "grossValue": 150000,
    }
    resp = client.post("/api/portfolios/no-such/operations", json=payload)
    assert resp.status_code == 404
