"""Tests for DeduplicationService."""

from __future__ import annotations

import pytest

from domain.deduplication import DeduplicationService
from domain.models import Operation


def _op(external_id: str, asset_code: str = "PETR4", date: str = "2024-01-01") -> Operation:
    return Operation(
        portfolio_id="p1",
        source="broker_csv",
        external_id=external_id,
        asset_code=asset_code,
        asset_type="stock",
        operation_type="buy",
        operation_date=date,
        quantity=100.0,
        unit_price=3500,
        gross_value=350000,
    )


@pytest.fixture
def svc() -> DeduplicationService:
    return DeduplicationService()


def test_no_duplicates(svc: DeduplicationService) -> None:
    ops = [_op("A"), _op("B"), _op("C")]
    unique, dups = svc.deduplicate(ops)
    assert len(unique) == 3
    assert dups == []


def test_exact_duplicate_removed(svc: DeduplicationService) -> None:
    ops = [_op("A"), _op("A")]
    unique, dups = svc.deduplicate(ops)
    assert len(unique) == 1
    assert len(dups) == 1


def test_different_dates_not_duplicate(svc: DeduplicationService) -> None:
    ops = [
        _op("A", date="2024-01-01"),
        _op("A", date="2024-01-02"),
    ]
    unique, dups = svc.deduplicate(ops)
    assert len(unique) == 2
    assert dups == []


def test_different_assets_not_duplicate(svc: DeduplicationService) -> None:
    ops = [_op("A", asset_code="PETR4"), _op("A", asset_code="VALE3")]
    unique, dups = svc.deduplicate(ops)
    assert len(unique) == 2


def test_first_occurrence_kept(svc: DeduplicationService) -> None:
    op1 = _op("A")
    op2 = _op("A")
    unique, dups = svc.deduplicate([op1, op2])
    assert unique[0] is op1
    assert dups[0] is op2


def test_empty_list(svc: DeduplicationService) -> None:
    unique, dups = svc.deduplicate([])
    assert unique == []
    assert dups == []


def test_custom_keys(svc: DeduplicationService) -> None:
    ops = [_op("A"), _op("B")]
    # deduplicate only by asset_code and operation_date — both ops are same asset+date
    unique, dups = svc.deduplicate(ops, keys=["asset_code", "operation_date"])
    assert len(unique) == 1
    assert len(dups) == 1
