"""Unit tests for ``domain.dividends_service.DividendsService``."""

from __future__ import annotations

from datetime import date

import pytest

from domain.dividends_service import DividendsService


def _op(
    *,
    asset_code: str,
    op_date: str,
    amount: int,
    op_type: str = "dividend",
    asset_name: str | None = None,
) -> dict:
    return {
        "asset_code": asset_code,
        "asset_name": asset_name or asset_code,
        "operation_type": op_type,
        "operation_date": op_date,
        "gross_value": amount,
    }


def test_summarise_groups_by_asset_month_and_type() -> None:
    ops = [
        _op(asset_code="ITSA4", op_date="2025-08-15", amount=20_000, op_type="dividend"),
        _op(asset_code="ITSA4", op_date="2025-11-15", amount=18_000, op_type="jcp"),
        _op(asset_code="ITSA4", op_date="2026-02-15", amount=22_000, op_type="dividend"),
        _op(asset_code="HGLG11", op_date="2025-09-15", amount=5_000, op_type="rendimento"),
        _op(asset_code="HGLG11", op_date="2025-10-15", amount=5_000, op_type="rendimento"),
    ]

    result = DividendsService().summarise(
        ops,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        portfolio_value_cents=1_000_000,
    )

    assert result["totals"]["total_received_cents"] == 70_000
    assert result["totals"]["events_count"] == 5

    by_asset = {a["asset_code"]: a for a in result["by_asset"]}
    # Ordering: largest first → ITSA4 (60_000) before HGLG11 (10_000).
    assert [a["asset_code"] for a in result["by_asset"]] == ["ITSA4", "HGLG11"]
    assert by_asset["ITSA4"]["total_cents"] == 60_000
    assert by_asset["HGLG11"]["total_cents"] == 10_000

    # Events inside each asset are sorted ascending by date.
    itsa_dates = [ev["date"] for ev in by_asset["ITSA4"]["events"]]
    assert itsa_dates == sorted(itsa_dates)

    by_type = result["by_type"]
    assert by_type["dividend_cents"] == 42_000
    assert by_type["jcp_cents"] == 18_000
    assert by_type["rendimento_cents"] == 10_000

    # Months sorted ascending.
    months = [m["month"] for m in result["by_month"]]
    assert months == sorted(months)


def test_summarise_excludes_operations_outside_window() -> None:
    ops = [
        _op(asset_code="ITSA4", op_date="2024-01-15", amount=10_000),  # too old
        _op(asset_code="ITSA4", op_date="2025-09-15", amount=20_000),  # in window
        _op(asset_code="ITSA4", op_date="2026-12-31", amount=30_000),  # in future
    ]
    result = DividendsService().summarise(
        ops,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
    )
    assert result["totals"]["total_received_cents"] == 20_000
    assert result["totals"]["events_count"] == 1


def test_summarise_skips_non_provent_operation_types() -> None:
    ops = [
        _op(asset_code="ITSA4", op_date="2025-09-15", amount=20_000, op_type="dividend"),
        _op(asset_code="ITSA4", op_date="2025-09-16", amount=99_999, op_type="buy"),
        _op(asset_code="ITSA4", op_date="2025-09-17", amount=99_999, op_type="amortization"),
    ]
    result = DividendsService().summarise(
        ops, period_start=date(2025, 1, 1), period_end=date(2026, 12, 31)
    )
    assert result["totals"]["total_received_cents"] == 20_000


def test_summarise_empty_window_yields_valid_empty_payload() -> None:
    result = DividendsService().summarise(
        [], period_start=date(2025, 4, 26), period_end=date(2026, 4, 25)
    )
    assert result["totals"]["total_received_cents"] == 0
    assert result["totals"]["events_count"] == 0
    assert result["by_asset"] == []
    assert result["by_month"] == []
    assert result["by_type"] == {
        "dividend_cents": 0,
        "jcp_cents": 0,
        "rendimento_cents": 0,
    }
    assert result["portfolio_dy_estimate"] is None


def test_summarise_dy_estimate_is_received_over_value() -> None:
    # 12 months received: 100_000 cents (R$1 000); portfolio worth R$10 000 → DY 10%.
    ops = [_op(asset_code="ITSA4", op_date="2025-09-15", amount=100_000)]
    result = DividendsService().summarise(
        ops,
        period_start=date(2025, 4, 26),
        period_end=date(2026, 4, 25),
        portfolio_value_cents=1_000_000,
    )
    dy = result["portfolio_dy_estimate"]
    assert dy is not None
    assert dy["value"] == 0.1000
    assert dy["portfolio_value_cents"] == 1_000_000
    assert "received_12m" in dy["method"]


def test_summarise_dy_disabled_when_value_missing_or_zero() -> None:
    ops = [_op(asset_code="ITSA4", op_date="2025-09-15", amount=100_000)]
    for value in (None, 0, -1):
        result = DividendsService().summarise(
            ops,
            period_start=date(2025, 4, 26),
            period_end=date(2026, 4, 25),
            portfolio_value_cents=value,
        )
        assert result["portfolio_dy_estimate"] is None


def test_summarise_monthly_average_uses_window_size() -> None:
    # 24-month window with R$240 → R$10/month average.
    ops = [
        _op(asset_code="ITSA4", op_date="2025-09-15", amount=12_000),
        _op(asset_code="ITSA4", op_date="2026-03-15", amount=12_000),
    ]
    result = DividendsService().summarise(
        ops,
        period_start=date(2024, 4, 26),
        period_end=date(2026, 4, 25),
    )
    assert result["period"]["months"] == 24
    assert result["totals"]["monthly_average_cents"] == 1_000


def test_summarise_rejects_inverted_window() -> None:
    with pytest.raises(ValueError):
        DividendsService().summarise(
            [], period_start=date(2026, 4, 25), period_end=date(2025, 4, 25)
        )
