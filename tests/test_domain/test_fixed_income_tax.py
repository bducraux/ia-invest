"""Tests for FixedIncomeTaxService — IR brackets and exemptions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.fixed_income_tax import FixedIncomeTaxService


@pytest.fixture
def tax() -> FixedIncomeTaxService:
    return FixedIncomeTaxService()


@pytest.mark.parametrize(
    "days,expected_rate",
    [
        (0, Decimal("0.225")),
        (30, Decimal("0.225")),
        (180, Decimal("0.225")),
        (181, Decimal("0.20")),
        (360, Decimal("0.20")),
        (361, Decimal("0.175")),
        (720, Decimal("0.175")),
        (721, Decimal("0.15")),
        (3650, Decimal("0.15")),
    ],
)
def test_cdb_pf_ir_table_brackets(
    tax: FixedIncomeTaxService, days: int, expected_rate: Decimal
) -> None:
    assert tax.get_ir_rate("CDB", "PF", days).rate == expected_rate


@pytest.mark.parametrize("asset", ["LCI", "LCA"])
def test_lci_lca_pf_is_exempt(tax: FixedIncomeTaxService, asset: str) -> None:
    rate = tax.get_ir_rate(asset, "PF", 30)
    assert rate.rate == Decimal("0")
    assert rate.label == "isento"


def test_calculate_ir_uses_correct_bracket(tax: FixedIncomeTaxService) -> None:
    # 200 days falls in 20% bracket
    ir = tax.calculate_estimated_ir("CDB", "PF", 200, Decimal("100"))
    assert ir == Decimal("20.00")


def test_calculate_ir_clamps_negative_income(tax: FixedIncomeTaxService) -> None:
    assert tax.calculate_estimated_ir("CDB", "PF", 30, Decimal("-50")) == Decimal("0")


def test_iof_is_zero_in_v1(tax: FixedIncomeTaxService) -> None:
    # V1 product decision — IOF intentionally ignored.
    assert tax.calculate_iof("CDB", "PF", 5, Decimal("1000")) == Decimal("0")


def test_unsupported_combination_raises(tax: FixedIncomeTaxService) -> None:
    with pytest.raises(ValueError):
        tax.get_ir_rate("FII", "PF", 30)
