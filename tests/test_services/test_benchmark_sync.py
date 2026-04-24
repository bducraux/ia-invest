"""Tests for BACENBenchmarkSyncService — uses mocked urlopen."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_server.services.benchmark_sync import (
    DEFAULT_BOOTSTRAP_START,
    BACENBenchmarkSyncService,
    BenchmarkSyncError,
)
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database


def _make_repo(tmp_path: Path) -> BenchmarkRatesRepository:
    db = Database(tmp_path / "test.db")
    db.initialize()
    return BenchmarkRatesRepository(db.connection)


def _fake_response(payload: object) -> BytesIO:
    body = json.dumps(payload).encode("utf-8")
    buf = BytesIO(body)

    class _Resp:
        def read(self) -> bytes:
            return buf.read()

        def __enter__(self):     # noqa: ANN001, ANN204
            return self

        def __exit__(self, *_args, **_kwargs) -> None:    # noqa: ANN001, ANN204
            return None

    return _Resp()    # type: ignore[return-value]


def test_sync_converts_percent_valor_to_fraction(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    payload = [
        {"data": "02/01/2024", "valor": "0.043739"},
        {"data": "03/01/2024", "valor": "0.043739"},
    ]
    with patch(
        "mcp_server.services.benchmark_sync.urlopen",
        return_value=_fake_response(payload),
    ):
        service = BACENBenchmarkSyncService(repo)
        result = service.sync(
            "CDI",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )

    assert result.rows_inserted == 2
    out = repo.get_range("CDI", date(2024, 1, 2), date(2024, 1, 3))
    # 0.043739 / 100 = 0.00043739 (percent → fraction)
    assert out[date(2024, 1, 2)] == Decimal("0.00043739")
    assert out[date(2024, 1, 3)] == Decimal("0.00043739")


def test_sync_url_is_built_with_brazilian_date_format(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    seen: dict[str, str] = {}

    def fake_urlopen(req, timeout):    # noqa: ANN001, ANN201, ARG001
        seen["url"] = req.full_url
        return _fake_response([])

    with patch("mcp_server.services.benchmark_sync.urlopen", side_effect=fake_urlopen):
        service = BACENBenchmarkSyncService(repo)
        service.sync("CDI", start_date=date(2024, 3, 4), end_date=date(2024, 3, 8))

    assert "bcdata.sgs.12" in seen["url"]
    assert "dataInicial=04%2F03%2F2024" in seen["url"]
    assert "dataFinal=08%2F03%2F2024" in seen["url"]
    assert "formato=json" in seen["url"]


def test_sync_incremental_starts_after_coverage_end(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [(date(2024, 5, 10), Decimal("0.0004"))])

    seen: dict[str, str] = {}

    def fake_urlopen(req, timeout):    # noqa: ANN001, ANN201, ARG001
        seen["url"] = req.full_url
        return _fake_response([])

    with patch("mcp_server.services.benchmark_sync.urlopen", side_effect=fake_urlopen):
        service = BACENBenchmarkSyncService(repo)
        service.sync("CDI", end_date=date(2024, 5, 20))

    # Incremental → start = coverage_end + 1 = 11/05/2024
    assert "dataInicial=11%2F05%2F2024" in seen["url"]


def test_sync_full_refresh_uses_bootstrap_default(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [(date(2025, 1, 1), Decimal("0.0004"))])

    seen: dict[str, str] = {}

    def fake_urlopen(req, timeout):    # noqa: ANN001, ANN201, ARG001
        seen["url"] = req.full_url
        return _fake_response([])

    with patch("mcp_server.services.benchmark_sync.urlopen", side_effect=fake_urlopen):
        service = BACENBenchmarkSyncService(repo)
        service.sync("CDI", end_date=date(2025, 6, 1), full_refresh=True)

    expected = DEFAULT_BOOTSTRAP_START.strftime("%d%%2F%m%%2F%Y")
    assert f"dataInicial={expected}" in seen["url"]


def test_sync_no_op_when_already_up_to_date(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.upsert_many("CDI", [(date(2024, 5, 20), Decimal("0.0004"))])

    with patch(
        "mcp_server.services.benchmark_sync.urlopen",
        side_effect=AssertionError("urlopen must not be called"),
    ):
        service = BACENBenchmarkSyncService(repo)
        result = service.sync(
            "CDI",
            start_date=date(2024, 5, 21),
            end_date=date(2024, 5, 20),
        )

    assert result.rows_inserted == 0
    assert result.source == "up_to_date"


def test_unsupported_benchmark_raises(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    service = BACENBenchmarkSyncService(repo)
    with pytest.raises(BenchmarkSyncError):
        service.sync("IPCA")


def test_malformed_response_raises(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch(
        "mcp_server.services.benchmark_sync.urlopen",
        return_value=_fake_response({"oops": "not a list"}),
    ):
        service = BACENBenchmarkSyncService(repo)
        with pytest.raises(BenchmarkSyncError):
            service.sync(
                "CDI",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
            )
