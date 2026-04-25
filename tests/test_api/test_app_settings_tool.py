"""Tests for the ``get_app_settings`` MCP tool and AppSettingsRepository."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from mcp_server.tools.app_settings import get_app_settings
from storage.repository.app_settings import AppSettingsRepository
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _seed_cdi(db: Database, daily: str = "0.000441", on: str = "2026-04-24") -> None:
    """Insert one CDI row in ``daily_benchmark_rates``."""
    BenchmarkRatesRepository(db.connection).upsert_many(
        "CDI", [(date.fromisoformat(on), Decimal(daily))]
    )


def _seed_selic(db: Database, daily: str = "0.000441", on: str = "2026-04-24") -> None:
    BenchmarkRatesRepository(db.connection).upsert_many(
        "SELIC", [(date.fromisoformat(on), Decimal(daily))]
    )


def _seed_ipca(
    db: Database,
    annual: str = "0.0451",
    reference_month: str = "2026-03",
) -> None:
    db.connection.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (AppSettingsRepository.IPCA_ANNUAL_RATE_KEY, annual),
    )
    db.connection.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (AppSettingsRepository.IPCA_REFERENCE_MONTH_KEY, reference_month),
    )
    db.connection.commit()


def test_returns_full_payload_when_all_rates_present(tmp_db: Database) -> None:
    _seed_cdi(tmp_db, daily="0.000441", on="2026-04-24")
    _seed_selic(tmp_db, daily="0.000441", on="2026-04-24")
    _seed_ipca(tmp_db, annual="0.0451", reference_month="2026-03")

    result = get_app_settings(tmp_db)

    rates = result["rates"]
    # Annualised: (1 + 0.000441)**252 - 1 ≈ 0.1175 — matches the prompt example.
    assert rates["cdi_annual"] == pytest.approx(0.1175, abs=1e-4)
    assert rates["selic_annual"] == pytest.approx(0.1175, abs=1e-4)
    assert rates["ipca_annual"] == pytest.approx(0.0451, abs=1e-6)
    assert rates["cdi_daily"] == pytest.approx(0.000441, abs=1e-9)
    assert rates["selic_daily"] == pytest.approx(0.000441, abs=1e-9)

    last_sync = result["last_sync"]
    assert last_sync["cdi"] == "2026-04-24"
    assert last_sync["selic"] == "2026-04-24"
    # IPCA: month → first day of the month in ISO YYYY-MM-DD.
    assert last_sync["ipca"] == "2026-03-01"

    # No warnings when everything is present.
    assert "warnings" not in result


def test_validates_iso_date_formats(tmp_db: Database) -> None:
    _seed_cdi(tmp_db, on="2026-04-24")
    _seed_selic(tmp_db, on="2026-04-23")
    _seed_ipca(tmp_db, reference_month="2026-03")

    result = get_app_settings(tmp_db)

    for key in ("cdi", "selic", "ipca"):
        value = result["last_sync"][key]
        assert isinstance(value, str)
        assert _ISO_DATE_RE.match(value), f"{key} sync date not ISO YYYY-MM-DD: {value!r}"

    assert _ISO_DATETIME_Z_RE.match(result["as_of"]), result["as_of"]


def test_rates_are_decimal_fractions_not_percent(tmp_db: Database) -> None:
    _seed_cdi(tmp_db, daily="0.000441")
    _seed_ipca(tmp_db, annual="0.0451")

    result = get_app_settings(tmp_db)
    assert result["rates"]["cdi_annual"] is not None
    # 11.75% must be encoded as ~0.1175, never 11.75.
    assert 0 < result["rates"]["cdi_annual"] < 1
    assert 0 < result["rates"]["ipca_annual"] < 1


def test_returns_null_when_ipca_missing(tmp_db: Database) -> None:
    _seed_cdi(tmp_db)
    _seed_selic(tmp_db)

    result = get_app_settings(tmp_db)
    assert result["rates"]["ipca_annual"] is None
    assert result["last_sync"]["ipca"] is None
    assert "ipca_unavailable" in result.get("warnings", [])


def test_returns_null_when_cdi_missing(tmp_db: Database) -> None:
    _seed_selic(tmp_db)
    _seed_ipca(tmp_db)

    result = get_app_settings(tmp_db)
    assert result["rates"]["cdi_annual"] is None
    assert result["rates"]["cdi_daily"] is None
    assert result["last_sync"]["cdi"] is None
    assert "cdi_unavailable" in result.get("warnings", [])
    # Other rates still present.
    assert result["rates"]["ipca_annual"] is not None


def test_returns_all_null_when_database_empty(tmp_db: Database) -> None:
    result = get_app_settings(tmp_db)

    assert result["rates"] == {
        "cdi_annual": None,
        "selic_annual": None,
        "ipca_annual": None,
        "cdi_daily": None,
        "selic_daily": None,
    }
    assert result["last_sync"] == {"cdi": None, "selic": None, "ipca": None}
    assert set(result.get("warnings", [])) == {
        "cdi_unavailable",
        "selic_unavailable",
        "ipca_unavailable",
    }


def test_picks_latest_cdi_row(tmp_db: Database) -> None:
    _seed_cdi(tmp_db, daily="0.000400", on="2026-04-22")
    _seed_cdi(tmp_db, daily="0.000441", on="2026-04-24")
    _seed_cdi(tmp_db, daily="0.000420", on="2026-04-23")

    result = get_app_settings(tmp_db)
    assert result["last_sync"]["cdi"] == "2026-04-24"
    assert result["rates"]["cdi_daily"] == pytest.approx(0.000441, abs=1e-9)


def test_repository_get_with_timestamp_returns_none_for_missing_key(
    tmp_db: Database,
) -> None:
    repo = AppSettingsRepository(tmp_db.connection)
    assert repo.get("missing") is None
    assert repo.get_with_timestamp("missing") is None
    assert repo.get_ipca_snapshot() is None
    assert repo.get_latest_daily_benchmark("CDI") is None
