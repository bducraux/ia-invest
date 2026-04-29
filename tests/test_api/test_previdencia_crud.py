"""CRUD tests for previdencia snapshot endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Portfolio
from domain.previdencia import PrevidenciaSnapshot
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository
from storage.repository.previdencia import PrevidenciaSnapshotRepository

PORTFOLIO_ID = "fundacao-ibm"
ASSET_CODE = "PREV_IBM_CD"


def _seed(db_path: Path) -> Database:
    db = Database(db_path)
    db.initialize()
    PortfolioRepository(db.connection).upsert(
        Portfolio(id=PORTFOLIO_ID, name="Fundacao IBM", base_currency="BRL", status="active")
    )
    PrevidenciaSnapshotRepository(db.connection).upsert_if_newer(
        PrevidenciaSnapshot(
            portfolio_id=PORTFOLIO_ID,
            asset_code=ASSET_CODE,
            product_name="IBM CD",
            quantity=9104.743,
            unit_price_cents=4751,
            market_value_cents=43260628,
            period_month="2026-03",
            period_start_date="2026-03-01",
            period_end_date="2026-03-31",
            source_file="extrato.pdf",
        )
    )
    return db


def _client(tmp_path: Path) -> tuple[TestClient, Database]:
    db_path = tmp_path / "ia.db"
    db = _seed(db_path)
    return TestClient(create_http_app(db_path, quotes_enabled=False)), db


def test_update_previdencia_snapshot(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/previdencia/{ASSET_CODE}",
        json={"marketValueCents": 50_000_000, "quantity": 10000.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["marketValueCents"] == 50_000_000
    assert body["quantity"] == 10000.0

    persisted = PrevidenciaSnapshotRepository(db.connection).get_by_asset(
        PORTFOLIO_ID, ASSET_CODE
    )
    assert persisted is not None
    assert persisted.market_value_cents == 50_000_000


def test_delete_previdencia_snapshot(tmp_path: Path) -> None:
    client, db = _client(tmp_path)
    resp = client.delete(f"/api/portfolios/{PORTFOLIO_ID}/previdencia/{ASSET_CODE}")
    assert resp.status_code == 204
    assert (
        PrevidenciaSnapshotRepository(db.connection).get_by_asset(
            PORTFOLIO_ID, ASSET_CODE
        )
        is None
    )


def test_update_unknown_returns_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/previdencia/UNKNOWN",
        json={"quantity": 1.0},
    )
    assert resp.status_code == 404


def test_update_with_empty_payload_returns_422(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    resp = client.patch(
        f"/api/portfolios/{PORTFOLIO_ID}/previdencia/{ASSET_CODE}", json={}
    )
    assert resp.status_code == 422
