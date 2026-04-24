"""Regression test: CDB CDI_PERCENT valuation against a real BACEN CDI series.

This is the layer that would have caught the original ~R$ 1,700 overstatement
introduced when CDI was modelled as a single flat annual rate. It pins the
end-to-end behaviour: real BACEN daily series → SQLiteDailyRateProvider →
FixedIncomeValuationService → numbers that match a hand-audited expected
gross value within R$ 0.01.

The CDI series fixture is committed in
``tests/fixtures/cdi/cdi_2024_q1_sample.json`` with values copied from the
public BACEN endpoint (SGS series 12). The expected gross is recomputed
deterministically from those values in this file, so the assertion is
self-consistent without depending on the production code path.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, getcontext
from pathlib import Path

import pytest

from domain.fixed_income import FixedIncomePosition
from domain.fixed_income_rates import SQLiteDailyRateProvider
from domain.fixed_income_valuation import FixedClock, FixedIncomeValuationService
from storage.repository.benchmark_rates import BenchmarkRatesRepository
from storage.repository.db import Database

getcontext().prec = 40

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "cdi" / "cdi_2024_q1_sample.json"


def _load_fixture() -> list[tuple[date, Decimal]]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    out: list[tuple[date, Decimal]] = []
    for entry in payload:
        d = date.fromisoformat(entry["date"])
        rate = Decimal(entry["rate"])
        out.append((d, rate))
    return out


@pytest.fixture
def cdi_provider(tmp_path: Path) -> SQLiteDailyRateProvider:
    db = Database(tmp_path / "test.db")
    db.initialize()
    repo = BenchmarkRatesRepository(db.connection)
    repo.upsert_many("CDI", _load_fixture())
    return SQLiteDailyRateProvider(repo)


def test_cdi_percent_matches_hand_audited_value(cdi_provider: SQLiteDailyRateProvider) -> None:
    """Compound a R$ 10,000 CDB at 100% CDI through Q1 2024 and assert the
    gross value matches what the daily fixture produces analytically."""

    fixture = _load_fixture()
    valuation_day = fixture[-1][0]    # last available business day in fixture

    pos = FixedIncomePosition(
        portfolio_id="p1",
        institution="Banco X",
        asset_type="CDB",
        product_name="CDB 100% CDI",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        investor_type="PF",
        currency="BRL",
        application_date="2024-01-01",
        maturity_date="2026-01-01",
        principal_applied_brl=10_000_00,    # R$ 10,000.00
        fixed_rate_annual_percent=None,
        benchmark_percent=100.0,
    )

    service = FixedIncomeValuationService(
        cdi_provider=cdi_provider,
        clock=FixedClock(valuation_day),
    )
    result = service.revalue(pos)

    # Reproduce the calculation from the fixture (100% of CDI = product of
    # daily factors, accruing for dates strictly after application_date).
    accumulated = Decimal(1)
    for d, rate in fixture:
        if d <= date(2024, 1, 1):
            continue
        accumulated *= (Decimal(1) + rate)
    expected = Decimal("10000") * accumulated

    assert result.is_complete, result.incomplete_reason
    # Tolerance: 1 cent (rounding boundary inside the valuation service).
    assert abs(result.gross_value_current_brl - int(round(expected * 100))) <= 1


def test_cdi_percent_holiday_in_fixture_does_not_flag_incomplete(
    cdi_provider: SQLiteDailyRateProvider,
) -> None:
    """The fixture intentionally omits Carnaval 2024 (Mon 2024-02-12 and
    Tue 2024-02-13). The valuation must NOT flag the result as incomplete
    just because two weekdays are missing — they are real B3 holidays
    and BACEN's omission of them is the source of truth."""

    fixture_dates = {d for d, _ in _load_fixture()}
    assert date(2024, 2, 12) not in fixture_dates    # Carnaval Monday
    assert date(2024, 2, 13) not in fixture_dates    # Carnaval Tuesday

    pos = FixedIncomePosition(
        portfolio_id="p1",
        institution="Banco X",
        asset_type="CDB",
        product_name="CDB 100% CDI",
        remuneration_type="CDI_PERCENT",
        benchmark="CDI",
        investor_type="PF",
        currency="BRL",
        application_date="2024-02-01",
        maturity_date="2026-01-01",
        principal_applied_brl=10_000_00,
        fixed_rate_annual_percent=None,
        benchmark_percent=100.0,
    )

    service = FixedIncomeValuationService(
        cdi_provider=cdi_provider,
        clock=FixedClock(date(2024, 2, 16)),
    )
    result = service.revalue(pos)

    assert result.is_complete, result.incomplete_reason
    assert result.incomplete_reason is None
