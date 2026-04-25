"""Unit tests for ``domain.portfolio_alerts_service``."""

from __future__ import annotations

from domain.portfolio_alerts_service import PortfolioAlertsService


def test_concentration_alerts_pass_through_with_source_tag() -> None:
    payload = PortfolioAlertsService().aggregate(
        concentration_alerts=[
            {"level": "critical", "code": "single_asset_high", "message": "ITSA4 ..."},
        ],
    )
    assert payload["total"] == 1
    assert payload["alerts"][0]["source"] == "concentration"
    assert payload["alerts"][0]["level"] == "critical"
    assert payload["counts"]["critical"] == 1


def test_upcoming_maturities_severity_threshold_at_7_days() -> None:
    payload = PortfolioAlertsService().aggregate(
        upcoming_maturities=[
            {
                "position_id": 1, "product_name": "CDB A",
                "maturity_date": "2026-05-01", "days_to_maturity": 6,
                "net_value_cents": 100_000,
            },
            {
                "position_id": 2, "product_name": "CDB B",
                "maturity_date": "2026-05-22", "days_to_maturity": 27,
                "net_value_cents": 200_000,
            },
        ],
    )
    by_pid = {a["details"]["position_id"]: a for a in payload["alerts"]}
    assert by_pid[1]["level"] == "warning"
    assert by_pid[2]["level"] == "info"


def test_missing_quote_assets_become_single_info_alert_sorted() -> None:
    payload = PortfolioAlertsService().aggregate(
        missing_quote_assets=["XPTO3", "ABC11", "XPTO3", ""],
    )
    assert payload["total"] == 1
    a = payload["alerts"][0]
    assert a["code"] == "missing_quotes"
    assert a["level"] == "info"
    assert a["details"]["assets"] == ["ABC11", "XPTO3"]


def test_incomplete_valuations_become_warnings() -> None:
    payload = PortfolioAlertsService().aggregate(
        incomplete_fixed_income_valuations=[
            {"position_id": 99, "product_name": "CDB Z", "reason": "série CDI incompleta"},
        ],
    )
    assert payload["total"] == 1
    assert payload["alerts"][0]["level"] == "warning"
    assert payload["alerts"][0]["code"] == "valuation_incomplete"


def test_alerts_sorted_by_severity_critical_warning_info() -> None:
    payload = PortfolioAlertsService().aggregate(
        concentration_alerts=[
            {"level": "info", "code": "top5_concentration", "message": "..."},
            {"level": "critical", "code": "single_asset_high", "message": "..."},
        ],
        missing_quote_assets=["A", "B"],
        upcoming_maturities=[
            {"position_id": 1, "product_name": "CDB A",
             "maturity_date": "2026-05-01", "days_to_maturity": 5,
             "net_value_cents": 100_000},
        ],
    )
    levels = [a["level"] for a in payload["alerts"]]
    assert levels == sorted(levels, key=lambda lv: {"critical": 0, "warning": 1, "info": 2}[lv])
    assert payload["counts"] == {"critical": 1, "warning": 1, "info": 2}


def test_empty_inputs_yield_empty_alerts() -> None:
    payload = PortfolioAlertsService().aggregate()
    assert payload == {"alerts": [], "counts": {"critical": 0, "warning": 0, "info": 0}, "total": 0}
