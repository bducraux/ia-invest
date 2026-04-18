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


def test_fetch_yahoo_parses_quote_response(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=True, ttl_seconds=300, timeout_seconds=0.1)

    seen_urls: list[str] = []

    def fake_fetch_json(url: str):
        seen_urls.append(url)
        if "chart/PETR4.SA" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 46.22,
                            }
                        }
                    ],
                }
            }
        return None

    service._fetch_json = fake_fetch_json  # type: ignore[method-assign]

    result = service._fetch_yahoo("PETR4")
    assert result == (4622, "yahoo")
    assert any("chart/PETR4.SA" in url for url in seen_urls)


def test_quote_service_uses_google_when_yahoo_fails(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=True, ttl_seconds=300, timeout_seconds=0.1)

    def fake_yahoo(code: str) -> tuple[int, str] | None:
        _ = code
        return None

    def fake_google(code: str) -> tuple[int, str] | None:
        assert code == "BBAS3"
        return 2440, "google"

    service._fetch_yahoo = fake_yahoo  # type: ignore[method-assign]
    service._fetch_google = fake_google  # type: ignore[method-assign]

    assert service.get_price_cents("BBAS3", "stock") == 2440


def test_fetch_google_parses_html_response(tmp_path: Path) -> None:
    db = Database(tmp_path / "quotes.db")
    db.initialize()

    service = MarketQuoteService(db.connection, enabled=True, ttl_seconds=300, timeout_seconds=0.1)

    html_response = '''
        <html>
        <body>
            <div data-last-price="21.26">BBDC4</div>
        </body>
        </html>
    '''

    def fake_urlopen(req, timeout=None):
        from unittest.mock import Mock
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_response.read = Mock(return_value=html_response.encode("utf-8"))
        return mock_response

    import mcp_server.services.quotes as quotes_module
    original_urlopen = quotes_module.urlopen
    quotes_module.urlopen = fake_urlopen  # type: ignore[attr-defined]

    try:
        result = service._fetch_google("BBDC4")
        assert result == (2126, "google")
    finally:
        quotes_module.urlopen = original_urlopen  # type: ignore[attr-defined]
