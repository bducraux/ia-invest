from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mcp_server.http_api import create_http_app
from storage.repository.asset_metadata import (
    AssetMetadata,
    AssetMetadataRepository,
)
from storage.repository.db import Database


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "api.db"
    db = Database(db_path)
    db.initialize()
    db.close()
    return TestClient(create_http_app(db_path, quotes_enabled=False))


def test_patch_creates_row_when_missing(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.patch(
        "/api/asset-metadata/itsa4",
        json={"cnpj": "61.532.644/0001-15"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assetCode"] == "ITSA4"
    assert body["cnpj"] == "61.532.644/0001-15"
    assert body["assetClassIrpf"] == "acao"
    assert body["source"] == "manual"


def test_patch_updates_existing_row(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    db = Database(db_path)
    db.initialize()
    AssetMetadataRepository(db.connection).upsert(
        AssetMetadata(
            asset_code="HGLG11",
            cnpj=None,
            asset_class_irpf="fii",
            asset_name_oficial=None,
            source="auto",
        )
    )
    db.close()
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.patch(
        "/api/asset-metadata/HGLG11",
        json={
            "cnpj": "11.728.688/0001-47",
            "assetNameOficial": "CSHG LOGÍSTICA FII",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cnpj"] == "11.728.688/0001-47"
    assert body["assetNameOficial"] == "CSHG LOGÍSTICA FII"
    assert body["source"] == "manual"
    assert body["assetClassIrpf"] == "fii"  # preservado


def test_patch_rejects_invalid_class(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.patch(
        "/api/asset-metadata/ITSA4",
        json={"assetClassIrpf": "invalida"},
    )
    assert response.status_code == 400


def test_patch_normalises_empty_string_to_null(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    db = Database(db_path)
    db.initialize()
    AssetMetadataRepository(db.connection).upsert(
        AssetMetadata(
            asset_code="ITSA4",
            cnpj="61.532.644/0001-15",
            asset_class_irpf="acao",
            asset_name_oficial=None,
            source="manual",
        )
    )
    db.close()
    client = TestClient(create_http_app(db_path, quotes_enabled=False))

    response = client.patch(
        "/api/asset-metadata/ITSA4",
        json={"cnpj": "   "},
    )
    assert response.status_code == 200
    assert response.json()["cnpj"] is None
