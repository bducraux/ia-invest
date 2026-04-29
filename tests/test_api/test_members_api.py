"""Tests for the HTTP API members endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from domain.members import Member
from domain.models import Portfolio
from mcp_server.http_api import create_http_app
from storage.repository.db import Database
from storage.repository.members import MemberRepository
from storage.repository.portfolios import PortfolioRepository


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "api.db"
    db = Database(db_path)
    db.initialize()
    m_repo = MemberRepository(db.connection)
    m_repo.upsert(Member(id="bruno", name="Bruno", email="bruno@example.com"))
    m_repo.upsert(Member(id="rafa", name="Rafa"))
    p_repo = PortfolioRepository(db.connection)
    p_repo.upsert(Portfolio(id="rv", name="RV", owner_id="bruno"))
    db.close()
    return TestClient(create_http_app(db_path, quotes_enabled=False))


def test_list_members(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/members")
    assert response.status_code == 200
    payload = response.json()
    ids = {m["id"] for m in payload}
    assert {"bruno", "rafa"}.issubset(ids)


def test_list_members_active_filter(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/members?status=active")
    assert response.status_code == 200
    assert all(m["status"] == "active" for m in response.json())


def test_get_member(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/members/bruno")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "bruno"
    assert payload["portfolioCount"] == 1


def test_create_member(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/members",
        json={"id": "ana", "name": "Ana", "email": "ana@example.com"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == "ana"
    assert payload["email"] == "ana@example.com"


def test_create_member_invalid_email(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/members", json={"id": "ana", "name": "Ana", "email": "bad"}
    )
    assert response.status_code == 422


def test_create_member_duplicate(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post("/api/members", json={"id": "bruno", "name": "X"})
    assert response.status_code == 422


def test_patch_member_changes_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.patch("/api/members/rafa", json={"name": "Rafael"})
    assert response.status_code == 200
    assert response.json()["name"] == "Rafael"


def test_patch_member_inactivate_blocked_when_owns_active(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.patch("/api/members/bruno", json={"status": "inactive"})
    assert response.status_code == 422


def test_delete_member_blocked_when_owns_portfolios(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.delete("/api/members/bruno")
    assert response.status_code == 409


def test_delete_member_succeeds_when_no_portfolios(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.delete("/api/members/rafa")
    assert response.status_code == 204


def test_get_member_portfolios(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/members/bruno/portfolios")
    assert response.status_code == 200
    portfolios = response.json()
    assert len(portfolios) == 1
    assert portfolios[0]["id"] == "rv"
    assert portfolios[0]["ownerId"] == "bruno"


def test_get_member_summary(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/members/bruno/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["member"]["id"] == "bruno"


def test_transfer_portfolio_owner_endpoint(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/portfolios/rv/transfer-owner", json={"newOwnerId": "rafa"}
    )
    assert response.status_code == 200
    assert response.json()["ownerId"] == "rafa"


def test_transfer_portfolio_owner_endpoint_unknown_member(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/portfolios/rv/transfer-owner", json={"newOwnerId": "ghost"}
    )
    assert response.status_code == 404


def test_list_portfolios_filter_by_owner(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/portfolios?ownerId=bruno")
    assert response.status_code == 200
    portfolios = response.json()
    assert all(p["ownerId"] == "bruno" for p in portfolios)


def test_update_portfolio_changes_owner(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.put(
        "/api/portfolios/rv",
        json={"name": "Renda Variável", "ownerId": "rafa"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Renda Variável"
    assert payload["ownerId"] == "rafa"


def test_update_portfolio_unknown_owner_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.put(
        "/api/portfolios/rv", json={"name": "X", "ownerId": "ghost"}
    )
    assert response.status_code == 422
