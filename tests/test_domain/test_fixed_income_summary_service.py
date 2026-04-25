"""Unit tests for ``domain.fixed_income_summary_service``."""

from __future__ import annotations

from datetime import date

from domain.fixed_income import FixedIncomePosition, FixedIncomeValuation
from domain.fixed_income_summary_service import (
    FixedIncomeSummaryService,
    ValuedFixedIncomePosition,
)


def _vp(
    *,
    pid: int,
    product: str = "CDB X",
    application: str = "2024-04-25",
    maturity: str = "2026-10-25",
    principal: int = 100_000,
    gross: int = 110_000,
    net: int = 108_000,
    ir: int = 2_000,
    status: str = "ACTIVE",
    is_complete: bool = True,
    incomplete_reason: str | None = None,
) -> ValuedFixedIncomePosition:
    pos = FixedIncomePosition(
        portfolio_id="renda-fixa",
        institution="Banco X",
        asset_type="CDB",
        product_name=product,
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        investor_type="PF",
        currency="BRL",
        application_date=application,
        maturity_date=maturity,
        principal_applied_brl=principal,
        benchmark_percent=110.0,
        status=status,
    )
    pos.id = pid
    val = FixedIncomeValuation(
        position_id=pid,
        valuation_date="2026-04-25",
        days_since_application=730,
        gross_value_current_brl=gross,
        gross_income_current_brl=gross - principal,
        estimated_ir_current_brl=ir,
        net_value_current_brl=net,
        tax_bracket_current="17.5%",
        is_complete=is_complete,
        incomplete_reason=incomplete_reason,
    )
    return ValuedFixedIncomePosition(position=pos, valuation=val)


def test_active_totals_sum_only_active_positions() -> None:
    payload = FixedIncomeSummaryService().summarise(
        [
            _vp(pid=1, principal=100_000, gross=110_000, net=108_000, ir=2_000),
            _vp(
                pid=2,
                product="CDB Vencido",
                maturity="2025-01-01",
                principal=50_000,
                gross=55_000,
                net=54_000,
                ir=1_000,
            ),
        ],
        as_of=date(2026, 4, 25),
    )
    a = payload["active_totals"]
    m = payload["matured_totals"]
    assert a["principal_cents"] == 100_000
    assert a["gross_value_cents"] == 110_000
    assert a["net_value_cents"] == 108_000
    assert a["estimated_ir_cents"] == 2_000
    assert a["count"] == 1
    assert m["principal_cents"] == 50_000
    assert m["net_value_cents"] == 54_000


def test_maturity_ladder_buckets_distribution() -> None:
    payload = FixedIncomeSummaryService().summarise(
        [
            _vp(pid=1, product="A", maturity="2026-05-10", principal=10_000, net=10_500),  # ~15d
            _vp(pid=2, product="B", maturity="2026-06-25", principal=20_000, net=21_000),  # ~61d
            _vp(pid=3, product="C", maturity="2026-12-01", principal=30_000, net=32_000),  # ~220d
            _vp(pid=4, product="D", maturity="2028-04-25", principal=40_000, net=44_000),  # ~2y
        ],
        as_of=date(2026, 4, 25),
    )
    by_bucket = {b["bucket"]: b for b in payload["maturity_ladder"]}
    assert by_bucket["le_30d"]["count"] == 1
    assert by_bucket["le_90d"]["count"] == 1
    assert by_bucket["le_365d"]["count"] == 1
    assert by_bucket["gt_365d"]["count"] == 1
    assert by_bucket["le_30d"]["principal_cents"] == 10_000


def test_upcoming_maturities_only_le_30_days_sorted() -> None:
    payload = FixedIncomeSummaryService().summarise(
        [
            _vp(pid=1, product="ZZ", maturity="2026-05-22", principal=10_000, net=10_500),  # 27d
            _vp(pid=2, product="AA", maturity="2026-05-01", principal=10_000, net=10_500),  # 6d
            _vp(pid=3, product="BB", maturity="2026-09-01", principal=10_000, net=10_500),  # too far
        ],
        as_of=date(2026, 4, 25),
    )
    upcoming = payload["upcoming_maturities"]
    assert [u["product_name"] for u in upcoming] == ["AA", "ZZ"]


def test_incomplete_valuation_is_surfaced() -> None:
    payload = FixedIncomeSummaryService().summarise(
        [
            _vp(
                pid=1,
                product="CDB Sem CDI",
                is_complete=False,
                incomplete_reason="série CDI incompleta",
            ),
        ],
        as_of=date(2026, 4, 25),
    )
    assert payload["incomplete_valuations"][0]["product_name"] == "CDB Sem CDI"
    assert "incompleta" in payload["incomplete_valuations"][0]["reason"]


def test_income_pct_is_zero_when_principal_zero() -> None:
    payload = FixedIncomeSummaryService().summarise([], as_of=date(2026, 4, 25))
    assert payload["active_totals"]["income_pct"] is None
    assert payload["positions"] == []


def test_income_pct_uses_net_minus_principal() -> None:
    payload = FixedIncomeSummaryService().summarise(
        [_vp(pid=1, principal=100_000, gross=120_000, net=115_000, ir=5_000)],
        as_of=date(2026, 4, 25),
    )
    # (115_000 - 100_000) / 100_000 = 0.15
    assert payload["active_totals"]["income_pct"] == 0.15
