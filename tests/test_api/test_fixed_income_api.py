"""Integration tests for the fixed-income HTTP endpoints."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient

from domain.models import Portfolio
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.portfolios import PortfolioRepository


def _seed(db_path: Path) -> None:
    db = Database(db_path)
    db.initialize()
    PortfolioRepository(db.connection).upsert(
        Portfolio(id="rf-portfolio", name="RF", base_currency="BRL", status="active")
    )


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "ia.db"
    _seed(db_path)
    return TestClient(create_http_app(db_path, quotes_enabled=False))


def test_create_and_list_fixed_income(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2026-01-02",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["assetType"] == "CDB"
    assert body["grossValueCurrentBrl"] >= body["principalAppliedBrl"]
    assert body["isComplete"] is True
    pos_id = body["id"]

    # List endpoint returns the new position with valuation fields populated.
    resp = client.get("/api/portfolios/rf-portfolio/fixed-income")
    assert resp.status_code == 200
    items = resp.json()["positions"]
    assert any(p["id"] == pos_id for p in items)

    # Detail endpoint returns same shape.
    resp = client.get(f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pos_id


def test_import_fixed_income_csv(tmp_path: Path) -> None:
    client = _client(tmp_path)

    csv_content = (
        "institution,asset_type,product_name,remuneration_type,application_date,"
        "maturity_date,application_value,benchmark,benchmark_percent,"
        "fixed_rate_annual_percent\n"
        "Banco X,LCI,LCI 95%,CDI_PERCENT,2024-01-02,2026-01-02,5000.00,CDI,95.0,\n"
        "Banco X,CDB,CDB Pre,PRE,2024-01-02,2026-01-02,1000.00,NONE,,12.0,\n"
        # Invalid: PRE without fixed rate
        "Banco X,CDB,Invalid,PRE,2024-01-02,2026-01-02,1000.00,NONE,,,\n"
    )
    files = {"file": ("rf.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post(
        "/api/portfolios/rf-portfolio/fixed-income/import-csv",
        files=files,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["failed"] == 1
    # LCI/LCA should always show as exempt.
    lci = next(p for p in data["positions"] if p["assetType"] == "LCI")
    assert lci["estimatedIrCurrentBrl"] == 0
    assert lci["taxBracketCurrent"] == "isento"


def test_summary_and_positions_include_fixed_income(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2027-01-02",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    positions_resp = client.get("/api/portfolios/rf-portfolio/positions")
    assert positions_resp.status_code == 200
    positions = positions_resp.json()["positions"]
    assert len(positions) == 1
    assert positions[0]["assetClass"] == "RENDA_FIXA"
    assert positions[0]["avgPrice"] == 1_000_000
    assert positions[0]["quoteSource"] == "fixed_income_valuation"

    summary_resp = client.get("/api/portfolios/rf-portfolio/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["totalInvested"] == 1_000_000
    assert summary["marketValue"] > 0
    assert any(slice_["assetClass"] == "RENDA_FIXA" for slice_ in summary["allocation"])


def test_positions_use_friendly_fixed_income_name(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "C6",
        "assetType": "CDB",
        "productName": "CDB 104% CDI",
        "remunerationType": "CDI_PERCENT",
        "applicationDate": "2024-01-02",
        "maturityDate": "2027-01-02",
        "principalAppliedBrl": 1_000_000,
        "benchmarkPercent": 104.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    positions_resp = client.get("/api/portfolios/rf-portfolio/positions")
    assert positions_resp.status_code == 200
    position = positions_resp.json()["positions"][0]

    assert position["assetClass"] == "RENDA_FIXA"
    assert position["name"] == "CDB C6 CDB 104% CDI"
    assert position["assetCode"].startswith("RF-")


def test_positions_filter_by_asset_class_for_fixed_income(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2027-01-02",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    positions_resp = client.get("/api/portfolios/rf-portfolio/positions?assetClass=RENDA_FIXA")
    assert positions_resp.status_code == 200
    positions = positions_resp.json()["positions"]

    assert len(positions) == 1
    assert positions[0]["assetClass"] == "RENDA_FIXA"


def test_fixed_income_uses_env_cdi_daily_rate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("IA_INVEST_CDI_DAILY_RATE", "0.0004")
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB 104 CDI",
        "remunerationType": "CDI_PERCENT",
        "applicationDate": "2024-01-02",
        "maturityDate": "2027-01-02",
        "principalAppliedBrl": 1_000_000,
        "benchmarkPercent": 104.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    listed = client.get("/api/portfolios/rf-portfolio/fixed-income").json()["positions"]
    item = listed[0]
    assert item["remunerationType"] == "CDI_PERCENT"
    assert item["isComplete"] is True
    assert item["grossValueCurrentBrl"] > item["principalAppliedBrl"]


def test_fixed_income_lifecycle_endpoints(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2024-01-12",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    pos_id = create_resp.json()["id"]

    # Toggle auto-reapply.
    toggle_resp = client.patch(
        f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}/auto-reapply",
        json={"enabled": True},
    )
    assert toggle_resp.status_code == 200, toggle_resp.text
    assert toggle_resp.json()["autoReapplyEnabled"] is True

    # Edit fields.
    edit_resp = client.patch(
        f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}",
        json={"notes": "edited", "productName": "CDB Pre 12 edit"},
    )
    assert edit_resp.status_code == 200, edit_resp.text
    assert edit_resp.json()["notes"] == "edited"

    # Redeem: creates a new position and deletes the old one.
    redeem_resp = client.post(
        f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}/redeem",
        json={"asOfDate": "2024-01-15"},
    )
    assert redeem_resp.status_code == 200, redeem_resp.text
    replacement = redeem_resp.json()
    assert replacement["applicationDate"] == "2024-01-15"
    assert replacement["maturityDate"] == "2024-01-25"
    assert replacement["id"] != pos_id

    # Old position must be gone.
    old_resp = client.get(f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}")
    assert old_resp.status_code == 404


def test_fixed_income_close_deletes_position(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2025-01-02",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    pos_id = create_resp.json()["id"]

    close_resp = client.delete(f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}")
    assert close_resp.status_code == 204, close_resp.text

    # Position must be gone.
    get_resp = client.get(f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}")
    assert get_resp.status_code == 404


def test_fixed_income_auto_reapply_runs_on_read_idempotently(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2024-01-12",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
        "autoReapplyEnabled": True,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    original_id = create_resp.json()["id"]

    # First read triggers reconcile: old is deleted, new is created.
    items_first = client.get("/api/portfolios/rf-portfolio/fixed-income").json()["positions"]
    # Second read: no more candidates, count stays the same.
    items_second = client.get("/api/portfolios/rf-portfolio/fixed-income").json()["positions"]

    assert len(items_first) == 1
    assert len(items_second) == 1

    # Original row is gone, the surviving row is the new position.
    assert all(item["id"] != original_id for item in items_second)
    assert items_second[0]["autoReapplyEnabled"] is True


def test_redeem_endpoint_creates_new_position(tmp_path: Path) -> None:
    client = _client(tmp_path)

    payload = {
        "institution": "Banco X",
        "assetType": "CDB",
        "productName": "CDB Pre 12%",
        "remunerationType": "PRE",
        "applicationDate": "2024-01-02",
        "maturityDate": "2026-01-02",
        "principalAppliedBrl": 1_000_000,
        "fixedRateAnnualPercent": 12.0,
    }
    create_resp = client.post("/api/portfolios/rf-portfolio/fixed-income", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    pos_id = create_resp.json()["id"]

    redeem_resp = client.post(
        f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}/redeem",
        json={"asOfDate": "2024-02-01"},
    )
    assert redeem_resp.status_code == 200, redeem_resp.text
    body = redeem_resp.json()
    # Redeem returns the NEW position (old one is deleted).
    assert body["id"] != pos_id
    assert body["status"] == "ACTIVE"
    assert body["applicationDate"] == "2024-02-01"
    assert body["principalAppliedBrl"] > 0

    # Old position must be gone.
    gone_resp = client.get(f"/api/portfolios/rf-portfolio/fixed-income/{pos_id}")
    assert gone_resp.status_code == 404
