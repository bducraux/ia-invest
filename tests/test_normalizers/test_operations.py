"""Tests for OperationNormalizer."""

from __future__ import annotations

import pytest

from normalizers.operations import OperationNormalizer
from domain.models import NormalizationResult


@pytest.fixture
def normalizer() -> OperationNormalizer:
    return OperationNormalizer()


def _raw(overrides: dict | None = None) -> dict:
    base = {
        "source": "broker_csv",
        "external_id": "OP001",
        "asset_code": "PETR4",
        "asset_type": "stock",
        "operation_type": "compra",
        "operation_date": "2024-01-15",
        "quantity": "100",
        "unit_price": "35,00",
        "gross_value": "3500,00",
        "fees": "1,50",
        "broker": "XP",
        "account": "12345",
    }
    if overrides:
        base.update(overrides)
    return base


def test_normalize_valid_record(normalizer: OperationNormalizer) -> None:
    result = normalizer.normalize([_raw()], "test-portfolio")
    assert len(result.valid) == 1
    assert result.errors == []

    op = result.valid[0]
    assert op.asset_code == "PETR4"
    assert op.operation_type == "buy"
    assert op.quantity == 100.0
    assert op.unit_price == 3500
    assert op.gross_value == 350000
    assert op.fees == 150


def test_normalize_date_formats(normalizer: OperationNormalizer) -> None:
    formats = ["2024-01-15", "15/01/2024", "15-01-2024"]
    for fmt in formats:
        result = normalizer.normalize([_raw({"operation_date": fmt})], "p")
        assert result.valid[0].operation_date == "2024-01-15", f"Failed for format: {fmt}"


def test_normalize_missing_asset_code_returns_error(normalizer: OperationNormalizer) -> None:
    result = normalizer.normalize([_raw({"asset_code": ""})], "test-portfolio")
    assert len(result.errors) == 1
    assert len(result.valid) == 0


def test_normalize_missing_date_returns_error(normalizer: OperationNormalizer) -> None:
    result = normalizer.normalize([_raw({"operation_date": ""})], "test-portfolio")
    assert len(result.errors) == 1


def test_normalize_unknown_operation_type_returns_error(
    normalizer: OperationNormalizer,
) -> None:
    result = normalizer.normalize([_raw({"operation_type": "xyzabc"})], "test-portfolio")
    assert len(result.errors) == 1


def test_normalize_infers_asset_type_when_missing(
    normalizer: OperationNormalizer,
) -> None:
    raw = _raw({"asset_type": "", "asset_code": "HGLG11"})
    result = normalizer.normalize([raw], "test-portfolio")
    assert result.valid[0].asset_type == "fii"


def test_normalize_derives_gross_from_price_and_qty(
    normalizer: OperationNormalizer,
) -> None:
    raw = _raw({"gross_value": "0", "unit_price": "35.00", "quantity": "100"})
    result = normalizer.normalize([raw], "p")
    assert result.valid[0].gross_value == 350000


def test_normalize_multiple_records(normalizer: OperationNormalizer) -> None:
    records = [_raw({"external_id": f"OP{i}"}) for i in range(5)]
    result = normalizer.normalize(records, "test-portfolio")
    assert len(result.valid) == 5
    assert result.errors == []


def test_normalize_mixed_valid_and_invalid(normalizer: OperationNormalizer) -> None:
    records = [
        _raw({"external_id": "OK1"}),
        _raw({"asset_code": ""}),   # invalid
        _raw({"external_id": "OK2"}),
    ]
    result = normalizer.normalize(records, "test-portfolio")
    assert len(result.valid) == 2
    assert len(result.errors) == 1
