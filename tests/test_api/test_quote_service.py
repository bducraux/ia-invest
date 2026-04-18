from __future__ import annotations

from pathlib import Path

from mcp_server.services.quotes import MarketQuoteService
from storage.repository.db import Database


def test_quote_service_uses_cache_after_first_fetch(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=True, ttl_seconds=300, timeout_seconds=0.1)

    calls = {"count": 0}

    def fake_fetch_live_quote(code: str, asset_type: str) -> tuple[int, str] | None:
        calls["count"] += 1
        assert code == "BBAS3"
        assert asset_type == "stock"
        return 2534, "fake"

    service._fetch_live_quote = fake_fetch_live_quote  # type: ignore[method-assign]

    first = service.get_price_cents("BBAS3", "stock")
    second = service.get_price_cents("BBAS3", "stock")

    assert first == 2534
    assert second == 2534
    assert calls["count"] == 1


def test_quote_service_returns_none_when_disabled(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=False)
    assert service.get_price_cents("BBAS3", "stock") is None


def test_quote_service_falls_back_to_none_on_provider_failure(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=True, ttl_seconds=300, timeout_seconds=0.1)

    def fake_fail_fetch(code: str, asset_type: str) -> tuple[int, str] | None:
        _ = code, asset_type
        return None

    service._fetch_live_quote = fake_fail_fetch  # type: ignore[method-assign]

    assert service.get_price_cents("BTC", "crypto") is None
